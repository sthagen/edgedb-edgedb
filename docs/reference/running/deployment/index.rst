.. _ref_guide_deployment:


==========
Deployment
==========

.. include:: ./note_cloud.rst

|Gel| can be hosted on all major cloud hosting platforms. The guides below
demonstrate how to spin up both a managed PostgreSQL instance and a container
running Gel `in Docker <https://github.com/geldata/gel-docker>`_.

.. note:: Minimum requirements

    As a rule of thumb, the Gel Docker container requires 1GB RAM! Images
    with insufficient RAM may experience unexpected issues during startup.

.. toctree::
    :maxdepth: 1

    aws_aurora_ecs
    azure_flexibleserver
    digitalocean
    fly_io
    gcp
    docker
    bare_metal
