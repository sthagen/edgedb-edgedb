use crate::{
    conn::{ConnError, ConnResult, Connector},
    metrics::MetricVariant,
    pool::{Pool, PoolConfig},
    PoolHandle,
};
use derive_more::{Add, AddAssign};
use pyo3::{
    exceptions::{PyException, PyValueError},
    prelude::*,
    types::PyByteArray,
};
use pyo3_util::{
    channel::{new_python_channel, PythonChannel, PythonChannelImpl, RustChannel},
    logging::{get_python_logger_level, initialize_logging_in_thread},
};
use serde_pickle::SerOptions;
use std::{
    cell::{Cell, RefCell},
    collections::BTreeMap,
    rc::Rc,
    sync::Arc,
    thread,
    time::{Duration, Instant},
};
use strum::IntoEnumIterator;
use tokio::task::LocalSet;
use tracing::{error, info, trace};

pyo3::create_exception!(_conn_pool, InternalError, PyException);

#[derive(Debug)]
enum RustToPythonMessage {
    Acquired(PythonConnId, ConnHandleId),
    Pruned(PythonConnId),

    PerformConnect(ConnHandleId, String),
    PerformDisconnect(ConnHandleId),
    PerformReconnect(ConnHandleId, String),

    Failed(PythonConnId, ConnHandleId),
    Metrics(Vec<u8>),
}

impl<'py> IntoPyObject<'py> for RustToPythonMessage {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        use RustToPythonMessage::*;
        let res = match self {
            Acquired(a, b) => (0, a, b.0).into_pyobject(py),
            PerformConnect(conn, s) => (1, conn.0, s).into_pyobject(py),
            PerformDisconnect(conn) => (2, conn.0).into_pyobject(py),
            PerformReconnect(conn, s) => (3, conn.0, s).into_pyobject(py),
            Pruned(conn) => (4, conn).into_pyobject(py),
            Failed(conn, error) => (5, conn, error.0).into_pyobject(py),
            Metrics(metrics) => {
                // This is not really fast but it should not be happening very often
                (6, PyByteArray::new(py, &metrics)).into_pyobject(py)
            }
        }?;
        Ok(res.into_any())
    }
}

#[derive(Debug)]
enum PythonToRustMessage {
    /// Acquire a connection.
    Acquire(PythonConnId, String),
    /// Release a connection.
    Release(PythonConnId),
    /// Discard a connection.
    Discard(PythonConnId),
    /// Prune connections from a database.
    Prune(PythonConnId, String),
    /// Completed an async request made by Rust.
    CompletedAsync(ConnHandleId),
    /// Failed an async request made by Rust.
    FailedAsync(ConnHandleId),
}

impl<'py> FromPyObject<'py> for PythonToRustMessage {
    fn extract_bound(_: &Bound<'py, PyAny>) -> PyResult<Self> {
        // Unused for this class
        Err(PyValueError::new_err("Not implemented"))
    }
}

type PythonConnId = u64;
#[derive(Debug, Default, Clone, Copy, Add, AddAssign, PartialEq, Eq, Hash, PartialOrd, Ord)]
struct ConnHandleId(u64);

impl From<ConnHandleId> for Box<(dyn std::error::Error + std::marker::Send + Sync + 'static)> {
    fn from(val: ConnHandleId) -> Self {
        Box::new(ConnError::Underlying(format!("{val:?}")))
    }
}

struct RpcPipe {
    channel: RustChannel<PythonToRustMessage, RustToPythonMessage>,
    handles: RefCell<BTreeMap<PythonConnId, PoolHandle<Rc<RpcPipe>>>>,
    next_id: Cell<ConnHandleId>,
    async_ops: RefCell<BTreeMap<ConnHandleId, tokio::sync::oneshot::Sender<()>>>,
}

impl std::fmt::Debug for RpcPipe {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("RpcPipe")
    }
}

impl RpcPipe {
    async fn call<T>(
        self: Rc<Self>,
        conn_id: ConnHandleId,
        ok: T,
        msg: RustToPythonMessage,
    ) -> ConnResult<T, ConnHandleId> {
        let (tx, rx) = tokio::sync::oneshot::channel();
        self.async_ops.borrow_mut().insert(conn_id, tx);
        self.channel
            .write(msg)
            .await
            .map_err(|_| ConnError::Underlying(conn_id))?;
        if rx.await.is_ok() {
            Err(ConnError::Underlying(conn_id))
        } else {
            Ok(ok)
        }
    }
}

impl Connector for Rc<RpcPipe> {
    type Conn = ConnHandleId;
    type Error = ConnHandleId;

    fn connect(
        &self,
        db: &str,
    ) -> impl futures::Future<
        Output = ConnResult<<Self as Connector>::Conn, <Self as Connector>::Error>,
    > + 'static {
        let id = self.next_id.get();
        self.next_id.set(id + ConnHandleId(1));
        let msg = RustToPythonMessage::PerformConnect(id, db.to_owned());
        self.clone().call(id, id, msg)
    }

    fn disconnect(
        &self,
        conn: Self::Conn,
    ) -> impl futures::Future<Output = ConnResult<(), <Self as Connector>::Error>> + 'static {
        self.clone()
            .call(conn, (), RustToPythonMessage::PerformDisconnect(conn))
    }

    fn reconnect(
        &self,
        conn: Self::Conn,
        db: &str,
    ) -> impl futures::Future<
        Output = ConnResult<<Self as Connector>::Conn, <Self as Connector>::Error>,
    > + 'static {
        self.clone().call(
            conn,
            conn,
            RustToPythonMessage::PerformReconnect(conn, db.to_owned()),
        )
    }
}

#[pyclass]
struct ConnPool {
    channel: Arc<PythonChannelImpl<PythonToRustMessage, RustToPythonMessage>>,
}

impl Drop for ConnPool {
    fn drop(&mut self) {
        info!("ConnPool dropped");
    }
}

fn internal_error(message: &str) -> PyErr {
    error!("{message}");
    InternalError::new_err(())
}

async fn run_and_block(config: PoolConfig, rpc_pipe: RpcPipe, stats_interval: f64) {
    let rpc_pipe = Rc::new(rpc_pipe);

    let pool = Pool::new(config, rpc_pipe.clone());

    let pool_task = {
        let pool = pool.clone();
        let rpc_pipe = rpc_pipe.clone();
        tokio::task::spawn_local(async move {
            let stats_interval = Duration::from_secs_f64(stats_interval);
            let mut last_stats = Instant::now();
            loop {
                pool.run_once();
                tokio::time::sleep(Duration::from_millis(10)).await;
                if last_stats.elapsed() > stats_interval {
                    last_stats = Instant::now();
                    if rpc_pipe
                        .channel
                        .write(RustToPythonMessage::Metrics(
                            serde_pickle::to_vec(&pool.metrics(), SerOptions::new())
                                .unwrap_or_default(),
                        ))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
            }
        })
    };

    loop {
        let Some(rpc) = rpc_pipe.channel.recv().await else {
            info!("ConnPool shutting down");
            pool_task.abort();
            pool.shutdown().await;
            break;
        };
        let pool = pool.clone();
        trace!("Received RPC: {rpc:?}");
        let rpc_pipe = rpc_pipe.clone();
        tokio::task::spawn_local(async move {
            use PythonToRustMessage::*;
            match rpc {
                Acquire(conn_id, db) => {
                    let conn = match pool.acquire(&db).await {
                        Ok(conn) => conn,
                        Err(ConnError::Underlying(err)) => {
                            _ = rpc_pipe
                                .channel
                                .write(RustToPythonMessage::Failed(conn_id, err))
                                .await;
                            return;
                        }
                        Err(_) => {
                            // TODO
                            return;
                        }
                    };
                    let handle = conn.handle();
                    rpc_pipe.handles.borrow_mut().insert(conn_id, conn);
                    _ = rpc_pipe
                        .channel
                        .write(RustToPythonMessage::Acquired(conn_id, handle))
                        .await;
                }
                Release(conn_id) => {
                    rpc_pipe.handles.borrow_mut().remove(&conn_id);
                }
                Discard(conn_id) => {
                    rpc_pipe
                        .handles
                        .borrow_mut()
                        .remove(&conn_id)
                        .unwrap()
                        .poison();
                }
                Prune(conn_id, db) => {
                    pool.drain_idle(&db).await;
                    _ = rpc_pipe
                        .channel
                        .write(RustToPythonMessage::Pruned(conn_id))
                        .await;
                }
                CompletedAsync(handle_id) => {
                    rpc_pipe.async_ops.borrow_mut().remove(&handle_id);
                }
                FailedAsync(handle_id) => {
                    _ = rpc_pipe
                        .async_ops
                        .borrow_mut()
                        .remove(&handle_id)
                        .unwrap()
                        .send(());
                }
            }
        });
    }
}

#[pymethods]
impl ConnPool {
    /// Create the connection pool and automatically boot a tokio runtime on a
    /// new thread. When this [`ConnPool`] is GC'd, the thread will be torn down.
    #[new]
    fn new(
        py: Python,
        max_capacity: usize,
        min_idle_time_before_gc: f64,
        stats_interval: f64,
    ) -> PyResult<Self> {
        let level = get_python_logger_level(py, "edb.server.conn_pool")?;
        let min_idle_time_before_gc = min_idle_time_before_gc as usize;
        let new = py.allow_threads(|| {
            let (txfd, rxfd) = std::sync::mpsc::channel();
            thread::spawn(move || {
                initialize_logging_in_thread("edb.server.conn_pool", level);
                info!("ConnPool::new(max_capacity={max_capacity}, min_idle_time_before_gc={min_idle_time_before_gc})");
                info!("Rust-side ConnPool thread booted");
                let rt = tokio::runtime::Builder::new_current_thread()
                    .enable_time()
                    .enable_io()
                    .build()
                    .unwrap();
                let _guard = rt.enter();

                let (rust, python) = new_python_channel();
                txfd.send(python).unwrap();
                let local = LocalSet::new();

                let rpc_pipe = RpcPipe {
                    channel: rust,
                    next_id: Default::default(),
                    handles: Default::default(),
                    async_ops: Default::default(),
                };

                let config = PoolConfig::suggested_default_for(max_capacity)
                    .with_min_idle_time_for_gc(Duration::from_secs(min_idle_time_before_gc as _));
                local.block_on(&rt, run_and_block(config, rpc_pipe, stats_interval));
            });

            let channel = rxfd.recv().unwrap().into();
            ConnPool {
                channel,
            }
        });
        Ok(new)
    }

    #[getter]
    fn _channel(&self) -> PyResult<PythonChannel> {
        Ok(PythonChannel::new(self.channel.clone()))
    }

    fn _acquire(&self, id: u64, db: &str) -> PyResult<()> {
        self.channel
            .send(PythonToRustMessage::Acquire(id, db.to_owned()))
            .map_err(|_| internal_error("In shutdown"))
    }

    fn _release(&self, id: u64) -> PyResult<()> {
        self.channel.send_err(PythonToRustMessage::Release(id))
    }

    fn _discard(&self, id: u64) -> PyResult<()> {
        self.channel.send_err(PythonToRustMessage::Discard(id))
    }

    fn _completed(&self, id: u64) -> PyResult<()> {
        self.channel
            .send_err(PythonToRustMessage::CompletedAsync(ConnHandleId(id)))
    }

    fn _failed(&self, id: u64, _error: PyObject) -> PyResult<()> {
        self.channel
            .send_err(PythonToRustMessage::FailedAsync(ConnHandleId(id)))
    }

    fn _prune(&self, id: u64, db: &str) -> PyResult<()> {
        self.channel
            .send_err(PythonToRustMessage::Prune(id, db.to_owned()))
    }
}

#[pymodule]
pub fn _conn_pool(py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    m.add_class::<ConnPool>()?;
    m.add("InternalError", py.get_type::<InternalError>())?;

    // Add each metric variant as a constant
    for variant in MetricVariant::iter() {
        m.add(
            format!("METRIC_{}", variant.as_ref().to_ascii_uppercase()).as_str(),
            variant as u32,
        )?;
    }

    Ok(())
}
