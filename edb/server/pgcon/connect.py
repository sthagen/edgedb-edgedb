#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2016-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import annotations

import logging
import textwrap

from edb.pgsql.common import quote_ident as pg_qi
from edb.pgsql.common import versioned_schema
from edb.pgsql import params as pg_params
from edb.server import pgcon

from . import errors as pgerror
from . import rust_transport

logger = logging.getLogger('edb.server')

INIT_CON_SCRIPT: bytes | None = None

# The '_edgecon_state table' is used to store information about
# the current session. The `type` column is one character, with one
# of the following values:
#
# * 'C': a session-level config setting
#
# * 'B': a session-level config setting that's implemented by setting
#   a corresponding Postgres config setting.
# * 'A': an instance-level config setting from command-line arguments
# * 'E': an instance-level config setting from environment variable
# * 'F': an instance/tenant-level config setting from the TOML config file
#
# * 'S': a session-level pg-ext config setting (frontend-only)
# * 'L': a transaction-level pg-ext config setting (frontend-only)
# * 'P': a session-level pg-ext config setting that's implemented by setting
#   a corresponding backend config setting (not stored in _edgecon_state)
#
# Please also update ConStateType in edb/server/config/__init__.py if changed.
SETUP_TEMP_TABLE_SCRIPT = '''
        CREATE TEMPORARY TABLE _edgecon_state (
            name text NOT NULL,
            value jsonb NOT NULL,
            type text NOT NULL CHECK(
                type = 'C' OR type = 'B' OR type = 'A' OR type = 'E'
                OR type = 'F' OR type = 'S' OR type = 'L'),
            UNIQUE(name, type)
        );
'''.strip()
SETUP_CONFIG_CACHE_SCRIPT = '''
        CREATE TEMPORARY TABLE _config_cache (
            source edgedb._sys_config_source_t,
            value edgedb._sys_config_val_t NOT NULL
        );
'''.strip()

# A empty dummy table used when we need to emit no-op DML.
#
# This is used by scan_check_ctes in the pgsql compiler to
# force the evaluation of error checking.
SETUP_DML_DUMMY_TABLE_SCRIPT = '''
        CREATE TEMPORARY TABLE _dml_dummy (
            id int8,
            flag bool,
            unique(id)
        );
        INSERT INTO _dml_dummy VALUES (0, false);
'''.strip()

RESET_STATIC_CFG_SCRIPT: bytes = b'''
    WITH x1 AS (
        DELETE FROM _config_cache
    )
    DELETE FROM _edgecon_state WHERE type = 'A' OR type = 'E' OR type = 'F';
'''


def _build_init_con_script(*, check_pg_is_in_recovery: bool) -> bytes:
    if check_pg_is_in_recovery:
        pg_is_in_recovery = ('''
        SELECT CASE WHEN pg_is_in_recovery() THEN
            edgedb.raise(
                NULL::bigint,
                'read_only_sql_transaction',
                msg => 'cannot use a hot standby'
            )
        END;
        ''').strip()
    else:
        pg_is_in_recovery = ''

    edgedb_schema = versioned_schema('edgedb')
    return textwrap.dedent(f'''
        {pg_is_in_recovery}

        {SETUP_TEMP_TABLE_SCRIPT}
        {SETUP_CONFIG_CACHE_SCRIPT}
        {SETUP_DML_DUMMY_TABLE_SCRIPT}

        CREATE CONSTRAINT TRIGGER _edgecon_state_local_reset
        AFTER INSERT ON _edgecon_state
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION {edgedb_schema}._clear_fe_local_sql_settings();

        PREPARE _clear_state AS
            WITH x1 AS (
                DELETE FROM _config_cache
            )
            DELETE FROM _edgecon_state
                WHERE type = 'C' OR type = 'B' or type = 'S';

        PREPARE _apply_state(jsonb) AS
            INSERT INTO
                _edgecon_state(name, value, type)
            SELECT
                (CASE
                    WHEN e->'type' = '"B"'::jsonb
                    THEN edgedb._apply_session_config(e->>'name', e->'value')
                    ELSE e->>'name'
                END) AS name,
                e->'value' AS value,
                e->>'type' AS type
            FROM
                jsonb_array_elements($1::jsonb) AS e;

        PREPARE _reset_session_config AS
            SELECT edgedb._reset_session_config();

        PREPARE _apply_sql_state(jsonb) AS
            WITH be AS (
                SELECT
                    pg_catalog.set_config(
                        e->>'name', e->>'value', false
                    ) AS value
                FROM
                    jsonb_array_elements($1::jsonb) AS e
                WHERE
                    e->'type' = '"P"'::jsonb
            ),
            fe AS (
                INSERT INTO
                    _edgecon_state(name, value, type)
                SELECT
                    e->>'name' AS name,
                    e->'value' AS value,
                    e->>'type' AS type
                FROM
                    jsonb_array_elements($1::jsonb) AS e
                WHERE
                    e->'type' = '"S"'::jsonb
                RETURNING 1
            )
            SELECT 1 FROM be, fe;

        PREPARE _set_sql_state(text, text, text) AS
            INSERT INTO
                _edgecon_state(name, type, value)
            VALUES
                ($1, $2, pg_catalog.to_jsonb($3))
            ON CONFLICT (name, type) DO UPDATE
                SET value = pg_catalog.to_jsonb($3);

        PREPARE _reset_sql_state(text, text) AS
            DELETE FROM
                _edgecon_state
            WHERE
                name = $1 AND type = $2;

        PREPARE _reset_sql_state_all AS
            DELETE FROM
                _edgecon_state
            WHERE
                type = 'S' OR type = 'L';
    ''').strip().encode('utf-8')


async def pg_connect(
    dsn_or_connection: str | rust_transport.ConnectionParams,
    *,
    backend_params: pg_params.BackendRuntimeParams,
    source_description: str,
    apply_init_script: bool = True,
) -> pgcon.PGConnection:
    global INIT_CON_SCRIPT

    if isinstance(dsn_or_connection, str):
        connection = rust_transport.ConnectionParams(dsn=dsn_or_connection)
    else:
        connection = dsn_or_connection

    # Note that we intentionally differ from the libpq connection behaviour
    # here: if we fail to connect with SSL enabled, we DO NOT retry with SSL
    # disabled.
    pgrawcon, pgconn = await rust_transport.create_postgres_connection(
        connection,
        lambda: pgcon.PGConnection(dbname=connection.database),
        source_description=source_description,
    )

    connection = pgrawcon.connection
    pgconn.connection = pgrawcon.connection
    pgconn.parameter_status = pgrawcon.state.parameters
    cancellation_key = pgrawcon.state.cancellation_key
    if cancellation_key:
        pgconn.backend_pid = cancellation_key[0]
        pgconn.backend_secret = cancellation_key[1]
    pgconn.is_ssl = pgrawcon.state.ssl
    pgconn.addr = pgrawcon.addr

    if (
        backend_params.has_create_role
        and backend_params.session_authorization_role
    ):
        sup_role = backend_params.session_authorization_role
        if connection.user != sup_role:
            # We used to use SET SESSION AUTHORIZATION here, there're some
            # security differences over SET ROLE, but as we don't allow
            # accessing Postgres directly through EdgeDB, SET ROLE is mostly
            # fine here. (Also hosted backends like Postgres on DigitalOcean
            # support only SET ROLE)
            await pgconn.sql_execute(f'SET ROLE {pg_qi(sup_role)}'.encode())

    if 'in_hot_standby' in pgconn.parameter_status:
        # in_hot_standby is always present in Postgres 14 and above
        if pgconn.parameter_status['in_hot_standby'] == 'on':
            # Abort if we're connecting to a hot standby
            pgconn.terminate()
            raise pgerror.BackendError(
                fields=dict(
                    M="cannot use a hot standby",
                    C=pgerror.ERROR_READ_ONLY_SQL_TRANSACTION,
                )
            )

    if apply_init_script:
        if INIT_CON_SCRIPT is None:
            INIT_CON_SCRIPT = _build_init_con_script(
                # On lower versions of Postgres we use pg_is_in_recovery() to
                # check if it is a hot standby, and error out if it is.
                check_pg_is_in_recovery=(
                    'in_hot_standby' not in pgconn.parameter_status
                ),
            )
        try:
            try:
                await pgconn.sql_execute(INIT_CON_SCRIPT)
            except pgcon.BackendError:
                from edb.pgsql import dbops, metaschema

                # ClearFELocalSQLSettingsFunction is needed by the
                # INIT_CON_SCRIPT, so we cannot simply patch it up
                # in the regular edb/pgsql/patches.py
                block = dbops.PLTopBlock()
                func = metaschema.ClearFELocalSQLSettingsFunction()
                dbops.CreateFunction(func, or_replace=True).generate(block)

                await pgconn.sql_execute(block.to_string().encode('utf-8'))
                await pgconn.sql_execute(INIT_CON_SCRIPT)
        except Exception:
            logger.exception(
                f"Failed to run init script for {pgconn.connection.to_dsn()}"
            )
            await pgconn.close()
            raise

    return pgconn
