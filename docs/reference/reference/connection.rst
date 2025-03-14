.. _ref_reference_connection:

=====================
Connection parameters
=====================

- :ref:`Instance parameters <ref_reference_connection_instance>`
- :ref:`Priority levels <ref_reference_connection_priority>`
- :ref:`Granular parameters <ref_reference_connection_granular>`


The CLI and client libraries (collectively referred to as "clients" below) must
connect to a Gel instance to run queries or commands. There are several
connection parameters, each of which can be specified in several ways.

.. _ref_reference_connection_instance:

Specifying an instance
----------------------

There are several ways to uniquely identify a Gel instance.

.. list-table::

  * - **Parameter**
    - **CLI flag**
    - **Environment variable**
  * - Instance name
    - ``--instance/-I <name>``
    - :gelenv:`INSTANCE`
  * - Secret key (required in some Gel Cloud scenarios; see description)
    - ``--secret-key``
    - :gelenv:`SECRET_KEY`
  * - DSN
    - ``--dsn <dsn>``
    - :gelenv:`DSN`
  * - Host and port
    - .. code-block::

        --host/-H <host>
        --port/-P <port>
    - :gelenv:`HOST` and :gelenv:`PORT`
  * - Credentials file
    - ``--credentials-file <path>``
    - :gelenv:`CREDENTIALS_FILE`
  * - *Project linking*
    - *N/A*
    - *N/A*


Let's dig into each of these a bit more.

.. _ref_reference_connection_instance_name:

**Instance name**
  All local instances (instances created on your local machine using the CLI)
  are associated with a name. This name is what's needed to connect; under the
  hood, the CLI stores the instance credentials (username, password, etc) on
  your file system in the Gel :ref:`config directory
  <ref_cli_gel_paths>`. The CLI and client libraries look up these
  credentials to connect.

  You can also assign names to remote instances using :ref:`gel instance
  link <ref_cli_gel_instance_link>`. The CLI will save the credentials
  locally, so you can connect to a remote instance using just its name, just
  like a local instance.

  If you have authenticated with Gel Cloud in the CLI using the
  :ref:`ref_cli_gel_cloud_login` command, you can address your own Gel
  Cloud instances using the instance name format
  ``<org-name>/<instance-name>``. If you are not authenticated,

.. _ref_reference_connection_secret_key:

**Secret key**
  If you want to connect to a Gel Cloud instance in either of these
  scenarios:

  - from a client binding
  - from the CLI to an instance not belonging to the currently authenticated
    Gel Cloud user

  you will need to provide a secret key in addition to the instance name.
  Generate a dedicated secret key for the instance via the CLI with
  :ref:`ref_cli_gel_cloud_secretkey_create` or via the web UI's "Secret
  Keys" pane in your instance dashboard.

**DSN**
  DSNs (data source names, also referred to as "connection strings") are a
  convenient and flexible way to specify connection information with a simple
  string. It takes the following form:

  * :geluri:`USERNAME:PASSWORD@HOSTNAME:PORT/BRANCH`
  * e.g.: :geluri:`alice:pa$$w0rd@example.com:1234/my_branch`

  All components of the DSN are optional; technically |geluri| is a valid
  DSN. The unspecified values will fall back to their defaults:

  * Host: ``"localhost"``
  * Port: ``5656``
  * User: |admin|
  * Password: ``null``
  * Branch name: |main|

  DSNs also accept query parameters to support advanced use cases. Read the
  :ref:`DSN Specification <ref_dsn>` reference for details.

**Host and port**
  In general, we recommend using a fully-qualified DSN when connecting to the
  database. For convenience, it's possible to individually specify a
  host and/or a port.

  When not otherwise specified, the host defaults to ``"localhost"`` and the
  port defaults to ``5656``.

**Credentials file**
  e.g. ``/path/to/credentials.json``.

  If you wish, you can store your credentials as a JSON file. Checking this
  file into version control could present a security risk and is not
  recommended.

  .. code-block:: json

    {
      "host": "localhost",
      "port": 10702,
      "user": "testuser",
      "password": "testpassword",
      "branch": "main",
      "tls_cert_data": "-----BEGIN CERTIFICATE-----\nabcdef..."
    }

  Relative paths are resolved relative to the current working directory.

**Project-linked instances**
  When you run :gelcmd:`project init` in a given directory, Gel creates an
  instance and "links" it to that directory. There's nothing magical about this
  link; it's just a bit of metadata that gets stored in the Gel config
  directory. When you use the client libraries or run a CLI command inside a
  project-linked directory, the library/CLI can detect this, look up the linked
  instance's credentials, and connect automatically.

  For more information on how this works, check out the `release post
  <https://www.geldata.com/blog/introducing-edgedb-projects>`_ for :gelcmd:`project`.

.. _ref_reference_connection_priority:

Priority levels
---------------

The section above describes the various ways of specifying a Gel instance.
There are also several ways to provide this configuration information to the
client. From highest to lowest priority, you can pass them explicitly as
parameters/flags (useful for debugging), use environment variables (recommended
for production), or rely on :gelcmd:`project` (recommended for development).

1. **Explicit connection parameters**. For security reasons,
   hard-coding connection information or credentials in your codebase is not
   recommended, though it may be useful for debugging or testing purposes. As
   such, explicitly provided parameters are given the highest priority.

   In the context of the client libraries, this means passing an option
   explicitly into the ``client creation`` call. Here's how this looks using the
   JavaScript library:

   .. code-block:: javascript

      import * as gel from "gel";

      const pool = await gel.createClient({
        instance: "my_instance"
      });

   In the context of the CLI, this means using the appropriate command-line
   flags:

   .. code-block:: bash

      $ gel --instance my_instance
      Gel x.x
      Type \help for help, \quit to quit.
      gel>


2. **Environment variables**.

   This is the recommended mechanism for providing connection information to
   your Gel client, especially in production or when running Gel inside a
   container. All clients read the following variables from the environment:

   - :gelenv:`DSN`
   - :gelenv:`INSTANCE`
   - :gelenv:`CREDENTIALS_FILE`
   - :gelenv:`HOST` / :gelenv:`PORT`

   When one of these environment variables is defined, there's no need to pass
   any additional information to the client. The CLI and client libraries will
   be able to connect without any additional information. You can execute CLI
   commands without any additional flags, like so:

   .. code-block:: bash

      $ gel  # no flags needed
      Gel x.x
      Type \help for help, \quit to quit.
      gel>

   Using the JavaScript client library:

   .. code-block:: javascript

      import { createClient } from "gel";

      const client = createClient();
      const result = await client.querySingle("select 2 + 2;");
      console.log(result); // 4

   .. warning::

      Ambiguity is not permitted. For instance, specifying both
      :gelenv:`INSTANCE` and :gelenv:`DSN` will result in an error. You *can*
      use :gelenv:`HOST` and :gelenv:`PORT` simultaneously.


3. **Project-linked credentials**

   If you are using :gelcmd:`project` (which we recommend!) and haven't
   otherwise specified any connection parameters, the CLI and client libraries
   will connect to the instance that's been linked to your project.

   This makes it easy to get up and running with Gel. Once you've run
   :gelcmd:`project init`, the CLI and client libraries will be able to
   connect to your database without any explicit flags or parameters, as long
   as you're inside the project directory.


If no connection information can be detected using the above mechanisms, the
connection fails.

.. warning::

   Within a given priority level, you cannot specify multiple instances of
   "instance selection parameters" simultaneously. For instance, specifying
   both :gelenv:`INSTANCE` and :gelenv:`DSN` environment variables will
   result in an error.


.. _ref_reference_connection_granular:

Granular parameters
-------------------

The :ref:`instance selection <ref_reference_connection_instance>` section
describes several mechanisms for providing a complete set of connection
information in a single package. Occasionally—perhaps in development or for
testing—it may be useful to override a particular *component* of this
configuration.

The following "granular" parameters will override any value set by the
instance-level configuration object.

.. list-table::

  * - **Environment variable**
    - **CLI flag**
  * - :gelenv:`BRANCH`
    - ``--branch/-b <name>``
  * - :gelenv:`USER`
    - ``--user/-u <user>``
  * - :gelenv:`PASSWORD`
    - ``--password <pass>``
  * - :gelenv:`TLS_CA_FILE`
    - ``--tls-ca-file <path>``
  * - :gelenv:`TLS_SERVER_NAME`
    - ``--tls-server-name``
  * - :gelenv:`CLIENT_TLS_SECURITY`
    - ``--tls-security``
  * - :gelenv:`CLIENT_SECURITY`
    - N/A

* :gelenv:`BRANCH`

  Each Gel *instance* can be branched multiple times. When an instance is
  created, a default branch named |main| is created. For CLI-managed
  instances, connections are made to the currently active branch. In other
  cases, incoming connections connect to the |main| branch by default.

* :gelenv:`USER` / :gelenv:`PASSWORD`

  These are the credentials of the database user account to connect to the
  Gel instance.

* :gelenv:`TLS_CA_FILE`

  TLS is required to connect to any Gel instance. To do so, the client needs
  a reference to the root certificate of your instance's certificate chain.
  Typically this will be handled for you when you create a local instance or
  ``link`` a remote one.

  If you're using a globally trusted CA like Let's Encrypt, the root
  certificate will almost certainly exist already in your system's global
  certificate pool. In this case, you won't need to specify this path; it will
  be discovered automatically by the client.

  If you're self-issuing certificates, you must download the root certificate
  and provide a path to its location on the filesystem. Otherwise TLS will fail
  to connect.

* :gelenv:`TLS_SERVER_NAME` (SNI)

  If for some reason target instance IP address can't be resolved from the
  hostname, you can provide SNI.

* :gelenv:`CLIENT_TLS_SECURITY`

  Sets the TLS security mode. Determines whether certificate and hostname
  verification is enabled. Possible values:

  - ``"strict"`` (**default**) — certificates and hostnames will be verified
  - ``"no_host_verification"`` — verify certificates but not hostnames
  - ``"insecure"`` — client libraries will trust self-signed TLS certificates.
    Useful for self-signed or custom certificates.

  This setting defaults to ``"strict"`` unless a custom certificate is
  supplied, in which case it is set to ``"no_host_verification"``.

* :gelenv:`CLIENT_SECURITY`

  Provides some simple "security presets".

  Currently there is only one valid value: ``insecure_dev_mode``. Setting
  :gelenv:`CLIENT_SECURITY=insecure_dev_mode` disables all TLS security
  measures. Currently it is equivalent to setting
  :gelenv:`CLIENT_TLS_SECURITY=insecure` but it may encompass additional
  configuration settings later.  This is most commonly used when developing
  locally with Docker.


.. _ref_reference_connection_granular_override:

Override behavior
^^^^^^^^^^^^^^^^^

When specified, the connection parameters (user, password, and |branch|)
will *override* the corresponding element of a DSN, credentials file, etc.
For instance, consider the following environment variables:

.. code-block::

  GEL_DSN=gel://olduser:oldpass@hostname.com:5656
  GEL_USER=newuser
  GEL_PASSWORD=newpass

In this scenario, ``newuser`` will override ``olduser`` and ``newpass``
will override ``oldpass``. The client library will try to connect using this
modified DSN: :geluri:`newuser:newpass@hostname.com:5656`.

Overriding across priority levels
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Override behavior can only happen at the *same or lower priority level*. For
instance:

- :gelenv:`PASSWORD` **will** override the password specified in
  :gelenv:`DSN`

- :gelenv:`PASSWORD` **will be ignored** if a DSN is passed
  explicitly using the ``--dsn`` flag. Explicit parameters take
  precedence over environment variables. To override the password of
  an explicit DSN, you need to pass it explicitly as well:

  .. code-block:: bash

     $ gel --dsn gel://username:oldpass@hostname.com --password qwerty
     # connects to gel://username:qwerty@hostname.com

- :gelenv:`PASSWORD` **will** override the stored password associated
  with a project-linked instance. (This is unlikely to be desirable.)
