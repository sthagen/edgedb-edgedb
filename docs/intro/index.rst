.. _ref_intro:

==============
Welcome to Gel
==============

.. toctree::
    :maxdepth: 3
    :hidden:

    installation
    quickstart/index
    tutorials/index
    guides/index
    localdev
    cli
    instances
    projects
    schema
    migrations
    branches
    edgeql
    clients

|Gel| is a next-generation `graph-relational database
<https://www.geldata.com/blog/the-graph-relational-database-defined>`_ designed
as a spiritual successor to the relational database.

It inherits the strengths of SQL databases: type safety, performance,
reliability, and transactionality. But instead of modeling data in a
relational (tabular) way, Gel represents data with *object types*
containing *properties* and *links* to other objects. It leverages
this object-oriented model to provide a superpowered query language that
solves some of SQL's biggest usability problems.

How to read the docs
^^^^^^^^^^^^^^^^^^^^

|Gel| is a complex system, but we've structured the documentation so you can
learn it in "phases". You only need to learn as much as you need to start
building your application.

- **Get Started** —
  Start with the :ref:`quickstart <ref_quickstart>`. It walks
  through Gel's core workflows: how to install Gel, create an instance,
  write a simple schema, execute a migration, write some simple queries, and
  use the client libraries. The rest of the section goes deeper on each of
  these subjects.

- **Schema** —
  A set of pages that break down the concepts of syntax of Gel's schema
  definition language (SDL). This starts with a rundown of Gel's primitive
  type system (:ref:`Primitives <ref_datamodel_primitives>`), followed by a
  description of (:ref:`Object Types <ref_datamodel_object_types>`) and the
  things they can contain: links, properties, indexes, access policies, and
  more.

- **EdgeQL** —
  A set of pages that break down Gel's query language, EdgeQL. It starts
  with a rundown of how to declare :ref:`literal values <ref_eql_literals>`,
  then introduces some key EdgeQL concepts like sets, paths, and type casts.
  With the basics established, it proceeds to break down all of EdgeQL's
  top-level statements: ``select``, ``insert``, and so on.

- **Guides** —
  Contains collections of guides on topics that are peripheral to Gel
  itself: how to deploy to various cloud providers, how to integrate with
  various frameworks, and how to introspect the schema to build
  code-generation tools on top of Gel.

- **Standard Library** —
  This section contains an encyclopedic breakdown of Gel's built-in types
  and the functions/operators that can be used with them. We didn't want to \
  clutter the **EdgeQL** section with all the nitty-gritty on each of these.
  If you're looking for a particular function (say, a ``replace``), go to the
  Standard Library page for the relevant type (in this case, :ref:`String
  <ref_std_string>`), and peruse the table for what you're looking for
  (:eql:func:`str_replace`).

- **Client Libraries**
  The documentation for Gel's set of official client libraries for
  JavaScript/TypeScript, Python, Go, and Rust. All client libraries implement
  Gel's binary protocol and provide a standard interface for executing
  queries. If you're using another language, you can execute queries
  :ref:`over HTTP <ref_edgeql_http>`.  This section also includes
  documentation for Gel's :ref:`GraphQL <ref_graphql_overview>` endpoint.

- **CLI**
  Complete reference for the |gelcmd| command-line tool. The CLI is
  self-documenting—add the ``--help`` flag after any command to print the
  relevant documentation—so you shouldn't need to reference this section often.

- **Reference**
  The *Reference* section contains a complete breakdown of Gel's *syntax*
  (for both EdgeQL and SDL), *internals* (like the binary protocol and dump
  file format), and *configuration settings*. Usually you'll only need to
  reference these once you're an advanced user.

- **Changelog**
  Detailed changelogs for each successive version of Gel, including any
  breaking changes, new features, bigfixes, and links to


Tooling
^^^^^^^

To actually build apps with Gel, you'll need to know more than SDL and
EdgeQL.

- **CLI** —
  The most commonly used CLI functionality is covered in the :ref:`Quickstart
  <ref_quickstart>`. For additional details, we have dedicated guides for
  :ref:`Migrations <ref_intro_migrations>` and :ref:`Projects
  <ref_guide_using_projects>`. A full CLI reference is available under
  :ref:`CLI <ref_cli_overview>`.

- **Client Libraries** —
  To actually execute queries, you'll use one of our client libraries for
  JavaScript, Go, or Python; find your preferred library under :ref:`Client
  Libraries <ref_clients_index>`. If you're using another language, you can
  still use Gel! You can execute :ref:`queries via HTTP <ref_edgeql_http>`.
- **Deployment** —
  To publish a Gel-backed application, you'll need to deploy Gel. Refer
  to :ref:`Guides > Deployment <ref_guide_deployment>` for step-by-step
  deployment guides for all major cloud hosting platforms, as well as
  instructions for self-hosting with Docker.

.. .. eql:react-element:: DocsNavTable

|Gel| features:

.. class:: ticklist

- strict, strongly typed schema;
- powerful and clean query language;
- ability to easily work with complex hierarchical data;
- built-in support for schema migrations.

|Gel| is not a graph database: the data is stored and queried using
relational database techniques.  Unlike most graph databases, Gel
maintains a strict schema.

|Gel| is not a document database, but inserting and querying hierarchical
document-like data is trivial.

|Gel| is not a traditional object database, despite the classification,
it is not an implementation of OOP persistence.

