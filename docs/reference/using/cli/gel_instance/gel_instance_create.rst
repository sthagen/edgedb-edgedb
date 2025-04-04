.. _ref_cli_gel_instance_create:


===================
gel instance create
===================

Initialize a new |Gel| instance.

.. cli:synopsis::

     gel instance create [<options>] [<name>] [<default-branch-or-database>]


Description
===========

:gelcmd:`instance create` is a terminal command for making a new Gel
instance and creating a corresponding credentials file in
``<gel_config_dir>/credentials``. Run :gelcmd:`info` to see the path to
``<gel_config_dir>`` on your machine.

.. note::

    The :gelcmd:`instance create` command is not intended for use with
    self-hosted instances. You can follow one of our :ref:`deployment guides
    <ref_guide_deployment>` for information on how to create one of these
    instances.


Gel Cloud
---------

Gel Cloud users may use this command to create a Cloud instance after
logging in using :ref:`ref_cli_gel_cloud_login`.

To create a Cloud instance, your instance name should be in the format
``<org-name>/<instance-name>``. Cloud instance names may contain alphanumeric
characters and hyphens (i.e., ``-``).

.. note::

    Please be aware of the following restrictions on |Gel| Cloud instance
    names:

    * can contain only Latin alpha-numeric characters or ``-``
    * cannot start with a dash (``-``) or contain double dashes (``--``)
    * maximum instance name length is 61 characters minus the length of your
      organization name (i.e., length of organization name + length of instance
      name must be fewer than 62 characters)


Options
=======

:cli:synopsis:`<name>`
    The new |Gel| instance name. Asked interactively if not specified.

:cli:synopsis:`<branch-or-database-name>`
    The default |branch| name on the new instance. Defaults
    to |main| or, when creating a pre-v5 instance, ``edgedb``.

:cli:synopsis:`--nightly`
    Use the nightly server for this instance.

:cli:synopsis:`--default-user=<default-user>`
    Specifies the default user name (created during initialization,
    and saved in credentials file). Defaults to: ``admin``,
    or, when creating a pre-v6 instance, ``edgedb``.

:cli:synopsis:`--port=<port>`
    Specifies which port should the instance be configured on. By
    default a random port will be used and recorded in the credentials
    file.

:cli:synopsis:`--start-conf=<start-conf>`
    Configures how the new instance should start: ``auto`` for
    automatic start with the system or user session, ``manual`` to
    turn that off so that the instance can be manually started with
    :ref:`ref_cli_gel_instance_start` on demand. Defaults to:
    ``auto``.

:cli:synopsis:`--channel=<channel>`
    Indicate the channel of the new instance. Possible values are ``stable``,
    ``testing``, or ``nightly``.

:cli:synopsis:`--version=<version>`
    Specifies the version of the |Gel| server to be used to run the
    new instance. To list the currently available options use
    :ref:`ref_cli_gel_server_list_versions`.

    By default, when you specify a version, the CLI will use the latest release
    in the major version specified. This command, for example, will install the
    latest X.Y release:

    .. code-block:: bash

        $ gel instance create --version X.0 demoxy

    You may pin to a specific version by prepending the version number with an
    equals sign. This command will install version X.Y:

    .. code-block:: bash

        $ gel instance create --version =X.Y demoxy

    .. note::

        Some shells like ZSH may require you to escape the equals sign (e.g.,
        ``\=X.Y``) or quote the version string (e.g., ``"=X.Y"``).

Gel Cloud options
-----------------

:cli:synopsis:`--region=<region>`
    The region in which to create the instance (for |Gel| Cloud instances).
    Possible values are ``aws-us-west-2``, ``aws-us-east-2``, and
    ``aws-eu-west-1``.

:cli:synopsis:`--tier=<tier>`
    Cloud instance subscription tier for the new instance. Possible values are
    ``pro`` and ``free``.

:cli:synopsis:`--compute-size=<number>`
    The size of compute to be allocated for the Gel Cloud instance (in
    Compute Units)

:cli:synopsis:`--storage-size=<GiB>`
    The size of storage to be allocated for the Cloud instance (in Gigabytes)
