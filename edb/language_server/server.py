#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
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

from typing import Mapping
import dataclasses
import pathlib
from pygls.server import LanguageServer
import pygls
from lsprotocol import types as lsp_types

from edb import errors
from edb.common import traceback as edb_traceback

from edb.edgeql import ast as qlast
from edb.edgeql import compiler as qlcompiler

from edb.ir import ast as irast

from edb.schema import schema as s_schema
from edb.schema import ddl as s_ddl

from . import project as ls_project
from . import utils as ls_utils
from . import parsing as ls_parsing
from . import is_edgeql_file, is_schema_file


@dataclasses.dataclass(kw_only=True)
class State:
    manifest: tuple[ls_project.Manifest, pathlib.Path] | None = None

    schema_docs: list[pygls.workspace.TextDocument] = dataclasses.field(
        default_factory=lambda: []
    )

    schema: s_schema.Schema | None = None

    std_schema: s_schema.Schema | None = None


@dataclasses.dataclass(kw_only=True)
class Config:
    project_dir: str


class GelLanguageServer(LanguageServer):
    state: State
    config: Config

    def __init__(self, config: Config):
        super().__init__("Gel Language Server", "v0.1")
        self.state = State()
        self.config = config


def send_internal_error(ls: GelLanguageServer, e: BaseException):
    text = edb_traceback.format_exception(e)
    ls.show_message_log(f'Internal error: {text}')


def document_updated(ls: GelLanguageServer, doc_uri: str):
    # each call to this function should yield in exactly one publish_diagnostics
    # for this document

    from . import schema as ls_schema

    document = ls.workspace.get_text_document(doc_uri)
    diagnostic_set: ls_utils.DiagnosticsSet

    try:
        if is_schema_file(doc_uri):
            # schema file

            diagnostics = ls_schema.update_schema_doc(ls, document)

            # recompile schema
            ls.state.schema = None
            _schema, diagnostic_set, err_msg = ls_schema.get_schema(ls)
            diagnostic_set.extend(document, diagnostics)

            if err_msg:
                ls.show_message(f'Error: {err_msg}')

        elif is_edgeql_file(doc_uri):
            # query file
            ql_ast_res = ls_parsing.parse(document)
            if diag := ql_ast_res.err:
                ls.publish_diagnostics(document.uri, diag, document.version)
                return
            assert ql_ast_res.ok is not None
            ql_ast = ql_ast_res.ok

            if isinstance(ql_ast, list):
                diagnostic_set, _ = compile(ls, document, ql_ast)
            else:
                # SDL in query files?
                diagnostic_set = ls_utils.DiagnosticsSet()
        else:
            ls.show_message_log(f'Unknown file type: {doc_uri}')
            diagnostic_set = ls_utils.DiagnosticsSet()
            # doc_uri in ('gel.toml')

        diagnostic_set.extend(document, [])  # make sure we publish for document
        for doc, diags in diagnostic_set.by_doc.items():
            ls.publish_diagnostics(doc.uri, diags, doc.version)
    except BaseException as e:
        send_internal_error(ls, e)
        ls.publish_diagnostics(document.uri, [], document.version)


def compile(
    ls: GelLanguageServer,
    doc: pygls.workspace.TextDocument,
    stmts: list[qlast.Base],
) -> tuple[ls_utils.DiagnosticsSet, list[irast.Statement]]:
    from . import schema as ls_schema

    if not stmts:
        return (ls_utils.DiagnosticsSet(by_doc={doc: []}), [])

    schema, diagnostics_set, err_msg = ls_schema.get_schema(ls)
    if not schema:
        if len(ls.state.schema_docs) == 0:
            diagnostics_set.append(
                doc,
                ls_utils.new_diagnostic_at_the_top(
                    err_msg or "Cannot find schema files"
                ),
            )
        return (diagnostics_set, [])

    diagnostics: list[lsp_types.Diagnostic] = []
    ir_stmts: list[irast.Statement] = []
    modaliases: Mapping[str | None, str] = {None: "default"}
    for ql_stmt in stmts:
        try:
            if isinstance(ql_stmt, qlast.DDLCommand):
                schema, _delta = s_ddl.delta_and_schema_from_ddl(
                    ql_stmt, schema=schema, modaliases=modaliases
                )

            elif isinstance(ql_stmt, (qlast.Command, qlast.Expr)):
                options = qlcompiler.CompilerOptions(modaliases=modaliases)
                ir_res = qlcompiler.compile_ast_to_ir(
                    ql_stmt, schema, options=options
                )
                if isinstance(ir_res, irast.Statement):
                    ir_stmts.append(ir_res)
            else:
                ls.show_message_log(f"skip compile of {ql_stmt}")
        except errors.EdgeDBError as error:
            diagnostics.append(ls_utils.error_to_lsp(error))

    diagnostics_set.extend(doc, diagnostics)
    return (diagnostics_set, ir_stmts)
