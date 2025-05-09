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


"""Context-agnostic SQL AST utilities."""


from __future__ import annotations

from typing import Optional, Iterator, Sequence, TYPE_CHECKING

from edb.ir import typeutils as irtyputils

from edb.pgsql import ast as pgast
from edb.pgsql import common
from edb.pgsql import types as pg_types

if TYPE_CHECKING:
    from typing_extensions import TypeGuard
    from edb.ir import ast as irast
    from . import context


def tuple_element_for_shape_el(
    shape_el: irast.Set,
    value: Optional[pgast.BaseExpr]=None,
    *,
    ctx: context.CompilerContextLevel
) -> pgast.TupleElementBase:
    from edb.ir import ast as irast

    if shape_el.path_id.is_type_intersection_path():
        assert isinstance(shape_el.expr, irast.Pointer)
        rptr = shape_el.expr.source.expr
    else:
        rptr = shape_el.expr
    assert isinstance(rptr, irast.Pointer)
    ptrref = rptr.ptrref
    ptrname = ptrref.shortname

    if value is not None:
        return pgast.TupleElement(
            path_id=shape_el.path_id,
            name=ptrname.name,
            val=value,
        )
    else:
        return pgast.TupleElementBase(
            path_id=shape_el.path_id,
            name=ptrname.name,
        )


def tuple_getattr(
    tuple_val: pgast.BaseExpr,
    tuple_typeref: irast.TypeRef,
    attr: str,
) -> pgast.BaseExpr:

    ttypes = []
    pgtypes = []
    for i, st in enumerate(tuple_typeref.subtypes):
        pgtype = pg_types.pg_type_from_ir_typeref(st)
        pgtypes.append(pgtype)

        if st.element_name:
            ttypes.append(st.element_name)
        else:
            ttypes.append(str(i))

    index = ttypes.index(attr)

    set_expr: pgast.BaseExpr

    if irtyputils.is_persistent_tuple(tuple_typeref):
        set_expr = pgast.Indirection(
            arg=tuple_val,
            indirection=[pgast.RecordIndirectionOp(name=attr)],
        )
    else:
        set_expr = pgast.SelectStmt(
            target_list=[
                pgast.ResTarget(
                    val=pgast.ColumnRef(
                        name=[str(index)],
                    ),
                ),
            ],
            from_clause=[
                pgast.RangeFunction(
                    functions=[
                        pgast.FuncCall(
                            name=('unnest',),
                            args=[
                                pgast.ArrayExpr(
                                    elements=[tuple_val],
                                )
                            ],
                            coldeflist=[
                                pgast.ColumnDef(
                                    name=str(i),
                                    typename=pgast.TypeName(
                                        name=t
                                    )
                                )
                                for i, t in enumerate(pgtypes)
                            ]
                        )
                    ]
                )
            ]
        )

    return set_expr


def array_get_inner_array(
    wrapped_array: pgast.BaseExpr,
    array_typeref: irast.TypeRef,
) -> pgast.BaseExpr:
    """Unwrap and get the inner array of a formerly nested array.

    Since array<array<...>> is implemented as array<tuple<array<...>>>, when
    an element is accessed, it needs to be unwrapped.

    Essentially, this function takes tuple<array<...>> and returns array<...>

    Postgres does not support arbitrarily accessing fields out of unnamed
    composites and so we need to do an extra unnest(array[]) to be able to
    specify the name and type our resulting array.

    For example, the query: `select [[1]][0];` will produce the following SQL:

    SELECT
            "expr-6~2"."array_value~4" AS "array_serialized~1"
        FROM
            LATERAL
            (SELECT
                    "expr-5~2"."array_value~3" AS "array_value~4"
                FROM
                    LATERAL
                    (SELECT
                            (SELECT
                                    "0"
                                FROM
                                    -- EXTRA unnest(array[])
                                    unnest(ARRAY[
                                        -- INDEX INDIRECTION
                                        edgedb_v7_2f26206480._index(
                                            "expr-3~2"."array_value~2",
                                            ($2)::int8,
                                            'ERROR MESSAGE'
                                        )
                                    ]) AS ("0" int8[])
                            ) AS "array_value~3"
                        FROM
                            LATERAL
                            -- INITAL ARRAY [[1]]
                            (SELECT
                                    ARRAY[ROW("expr-2~2"."array_value~1")]
                                    AS "array_value~2"
                                FROM
                                    LATERAL
                                    (SELECT
                                            ARRAY[($1)::int8]
                                            AS "array_value~1"
                                    ) AS "expr-2~2"
                            ) AS "expr-3~2"
                    ) AS "expr-5~2"
            ) AS "expr-6~2"
        WHERE
            ("expr-6~2"."array_value~4" IS NOT NULL)
        LIMIT
        (SELECT
                (101)::int8 AS "expr~7_value~1"
        )
    """
    return pgast.SelectStmt(
        target_list=[
            pgast.ResTarget(val=pgast.ColumnRef(name=['0'])),
        ],
        from_clause=[
            pgast.RangeFunction(
                functions=[
                    pgast.FuncCall(
                        name=('unnest',),
                        args=[
                            pgast.ArrayExpr(
                                elements=[wrapped_array],
                            )
                        ],
                        coldeflist=[
                            pgast.ColumnDef(
                                name='0',
                                typename=pgast.TypeName(
                                    name=pg_types.pg_type_from_ir_typeref(array_typeref)
                                )
                            )
                        ]
                    )
                ]
            )
        ]
    )


def is_null_const(expr: pgast.BaseExpr) -> bool:
    if isinstance(expr, pgast.TypeCast):
        expr = expr.arg
    return isinstance(expr, pgast.NullConstant)


def is_set_op_query(query: pgast.BaseExpr) -> TypeGuard[pgast.SelectStmt]:
    return (
        isinstance(query, pgast.SelectStmt)
        and query.op is not None
    )


def get_leftmost_query(query: pgast.Query) -> pgast.Query:
    result = query
    while is_set_op_query(result):
        assert result.larg
        result = result.larg
    return result


def each_query_in_set(qry: pgast.Query) -> Iterator[pgast.Query]:
    # We do this iteratively instead of recursively (with yield from)
    # to avoid being pointlessly quadratic.
    stack = [qry]
    while stack:
        qry = stack.pop()
        if is_set_op_query(qry):
            assert qry.larg and qry.rarg
            stack.append(qry.rarg)
            stack.append(qry.larg)
        else:
            yield qry


def each_base_rvar(rvar: pgast.BaseRangeVar) -> Iterator[pgast.BaseRangeVar]:
    # We do this iteratively instead of recursively (with yield from)
    # to avoid being pointlessly quadratic.
    stack = [rvar]
    while stack:
        rvar = stack.pop()
        if isinstance(rvar, pgast.JoinExpr):
            for clause in reversed(rvar.joins):
                stack.append(clause.rarg)
            stack.append(rvar.larg)
        else:
            yield rvar


def new_binop(
    lexpr: pgast.BaseExpr,
    rexpr: pgast.BaseExpr,
    op: str,
) -> pgast.Expr:
    return pgast.Expr(
        name=op,
        lexpr=lexpr,
        rexpr=rexpr
    )


def extend_binop(
    binop: Optional[pgast.BaseExpr],
    *exprs: pgast.BaseExpr,
    op: str = 'AND',
) -> pgast.BaseExpr:
    exprlist = list(exprs)
    result: pgast.BaseExpr

    if binop is None:
        result = exprlist.pop(0)
    else:
        result = binop

    for expr in exprlist:
        if expr is not None and expr is not result:
            result = new_binop(lexpr=result, op=op, rexpr=expr)

    return result


def extend_concat(
    expr: str | pgast.BaseExpr, *exprs: str | pgast.BaseExpr
) -> pgast.BaseExpr:
    return extend_binop(
        pgast.StringConstant(val=expr) if isinstance(expr, str) else expr,
        *[
            pgast.StringConstant(val=e) if isinstance(e, str) else e
            for e in exprs
        ],
        op='||',
    )


def new_coalesce(
    expr: pgast.BaseExpr, fallback: pgast.BaseExpr
) -> pgast.BaseExpr:
    return pgast.FuncCall(name=('coalesce',), args=[expr, fallback])


def extend_select_op(
    stmt: Optional[pgast.SelectStmt],
    *stmts: pgast.SelectStmt,
    op: str = 'UNION',
) -> Optional[pgast.SelectStmt]:
    stmt_list = list(stmts)
    result: pgast.SelectStmt

    if stmt is None:
        if len(stmt_list) == 0:
            return None
        result = stmt_list.pop(0)
    else:
        result = stmt

    for s in stmt_list:
        if s is not None and s is not result:
            result = pgast.SelectStmt(larg=result, op=op, rarg=s)

    return result


def new_unop(op: str, expr: pgast.BaseExpr) -> pgast.Expr:
    return pgast.Expr(name=op, rexpr=expr)


def join_condition(
    lref: pgast.ColumnRef,
    rref: pgast.ColumnRef,
) -> pgast.BaseExpr:
    path_cond: pgast.BaseExpr = new_binop(lref, rref, op='=')

    if lref.optional:
        opt_cond = pgast.NullTest(arg=lref)
        path_cond = extend_binop(path_cond, opt_cond, op='OR')

    if rref.optional:
        opt_cond = pgast.NullTest(arg=rref)
        path_cond = extend_binop(path_cond, opt_cond, op='OR')

    return path_cond


def safe_array_expr(
    elements: list[pgast.BaseExpr],
    *,
    ser_safe: bool = False,
    ctx: context.CompilerContextLevel,
) -> pgast.BaseExpr:
    result: pgast.BaseExpr = pgast.ArrayExpr(
        elements=elements,
        ser_safe=ser_safe,
    )
    if any(el.nullable for el in elements):
        result = pgast.FuncCall(
            name=edgedb_func('_nullif_array_nulls', ctx=ctx),
            args=[result],
            ser_safe=ser_safe,
        )
    return result


def find_column_in_subselect_rvar(
    rvar: pgast.RangeSubselect,
    name: str,
) -> int:
    # Range over a subquery, we can inspect the output list
    # of the subquery.  If the subquery is a UNION (or EXCEPT),
    # we take the leftmost non-setop query.
    subquery = get_leftmost_query(rvar.subquery)
    for i, rt in enumerate(subquery.target_list):
        if rt.name == name:
            return i

    raise RuntimeError(f'cannot find {name!r} in {rvar} output')


def get_column(
    rvar: pgast.BaseRangeVar,
    colspec: str | pgast.ColumnRef,
    *,
    is_packed_multi: bool = True,
    nullable: Optional[bool] = None,
) -> pgast.ColumnRef:

    if isinstance(colspec, pgast.ColumnRef):
        colname = colspec.name[-1]
    else:
        colname = colspec

    assert isinstance(colname, str)

    ser_safe = False

    if nullable is None:
        if isinstance(rvar, pgast.RelRangeVar):
            # Range over a relation, we cannot infer nullability in
            # this context, so assume it's true, unless we are looking
            # at a colspec that says it is false
            if isinstance(colspec, pgast.ColumnRef):
                nullable = colspec.nullable
            else:
                nullable = True

        elif isinstance(rvar, pgast.RangeSubselect):
            col_idx = find_column_in_subselect_rvar(rvar, colname)
            if is_set_op_query(rvar.subquery):
                nullables = []
                ser_safes = []

                for q in each_query_in_set(rvar.subquery):
                    nullables.append(q.target_list[col_idx].nullable)
                    ser_safes.append(q.target_list[col_idx].ser_safe)

                nullable = any(nullables)
                ser_safe = all(ser_safes)
            else:
                rt = rvar.subquery.target_list[col_idx]
                nullable = rt.nullable
                ser_safe = rt.ser_safe

        elif isinstance(rvar, pgast.RangeFunction):
            # Range over a function.
            # TODO: look into the possibility of inspecting coldeflist.
            nullable = True

        elif isinstance(rvar, pgast.JoinExpr):
            raise RuntimeError(
                f'cannot find {colname!r} in unexpected {rvar!r} range var')

    name = [rvar.alias.aliasname, colname]

    return pgast.ColumnRef(
        name=name, nullable=nullable, ser_safe=ser_safe,
        is_packed_multi=is_packed_multi)


def get_rvar_var(
    rvar: pgast.BaseRangeVar, var: pgast.OutputVar
) -> pgast.OutputVar:

    fieldref: pgast.OutputVar

    if isinstance(var, pgast.TupleVarBase):
        elements = []

        for el in var.elements:
            assert isinstance(el.name, pgast.OutputVar)
            val = get_rvar_var(rvar, el.name)
            elements.append(
                pgast.TupleElement(
                    path_id=el.path_id, name=el.name, val=val))

        fieldref = pgast.TupleVar(
            elements,
            named=var.named,
            typeref=var.typeref,
            is_packed_multi=var.is_packed_multi,
        )

    elif isinstance(var, pgast.ColumnRef):
        fieldref = get_column(rvar, var, is_packed_multi=var.is_packed_multi)

    elif isinstance(var, pgast.ExprOutputVar):
        fieldref = var

    else:
        raise AssertionError(f'unexpected OutputVar subclass: {var!r}')

    return fieldref


def strip_output_var(
    var: pgast.OutputVar,
    *,
    optional: Optional[bool] = None,
    nullable: Optional[bool] = None,
) -> pgast.OutputVar:

    result: pgast.OutputVar

    if isinstance(var, pgast.TupleVarBase):
        elements = []

        for el in var.elements:
            val: pgast.OutputVar
            el_name = el.name

            if isinstance(el_name, str):
                val = pgast.ColumnRef(name=[el_name])
            elif isinstance(el_name, pgast.OutputVar):
                val = strip_output_var(el_name)
            else:
                raise AssertionError(
                    f'unexpected tuple element class: {el_name!r}')

            elements.append(
                pgast.TupleElement(
                    path_id=el.path_id, name=el_name, val=val))

        result = pgast.TupleVar(
            elements,
            named=var.named,
            typeref=var.typeref,
        )

    elif isinstance(var, pgast.ColumnRef):
        result = pgast.ColumnRef(
            name=[var.name[-1]],
            optional=optional if optional is not None else var.optional,
            nullable=nullable if nullable is not None else var.nullable,
        )

    else:
        raise AssertionError(f'unexpected OutputVar subclass: {var!r}')

    return result


def select_is_simple(stmt: pgast.SelectStmt) -> bool:
    return (
        not stmt.distinct_clause
        and not stmt.where_clause
        and not stmt.group_clause
        and not stmt.having_clause
        and not stmt.window_clause
        and not stmt.values
        and not stmt.sort_clause
        and not stmt.limit_offset
        and not stmt.limit_count
        and not stmt.locking_clause
        and not stmt.op
    )


def is_row_expr(expr: pgast.BaseExpr) -> bool:
    while True:
        if isinstance(expr, (pgast.RowExpr, pgast.ImplicitRowExpr)):
            return True
        elif isinstance(expr, pgast.TypeCast):
            expr = expr.arg
        else:
            return False


def _get_target_from_range(
    target: pgast.BaseExpr, rvar: pgast.BaseRangeVar
) -> Optional[pgast.BaseExpr]:
    """Try to read a target out of a very simple rvar.

    The goal here is to allow collapsing trivial pass-through subqueries.
    In particular, given a target `foo.bar` and an rvar
    `(SELECT <expr> as "bar") AS "foo"`, we produce <expr>.

    We can also recursively handle the nested case.
    """
    if (
        not isinstance(rvar, pgast.RangeSubselect)

        # Check that the relation name matches the rvar
        or not isinstance(target, pgast.ColumnRef)
        or not target.name
        or target.name[0] != rvar.alias.aliasname

        # And that the rvar is a simple subquery with one target
        # and at most one from clause
        or not (subq := rvar.subquery)
        or len(subq.target_list) != 1
        or not isinstance(subq, pgast.SelectStmt)
        or not select_is_simple(subq)
        or len(subq.from_clause) > 1

        # And that the one target matches
        or not (inner_tgt := rvar.subquery.target_list[0])
        or inner_tgt.name != target.name[1]
    ):
        return None

    if subq.from_clause:
        return _get_target_from_range(inner_tgt.val, subq.from_clause[0])
    else:
        return inner_tgt.val


def collapse_query(query: pgast.Query) -> pgast.BaseExpr:
    """Try to collapse trivial queries into simple expressions.

    In particular, we want to transform
    `(SELECT foo.bar FROM LATERAL (SELECT <expr> as "bar") AS "foo")`
    into simply `<expr>`.
    """
    if not isinstance(query, pgast.SelectStmt):
        return query

    if (
        isinstance(query, pgast.SelectStmt)
        and len(query.target_list) == 1
        and len(query.from_clause) == 0
        and select_is_simple(query)
    ):
        return query.target_list[0].val

    if (
        not isinstance(query, pgast.SelectStmt)
        or len(query.target_list) != 1
        or len(query.from_clause) != 1
    ):
        return query

    val = _get_target_from_range(
        query.target_list[0].val, query.from_clause[0])
    if val:
        return val
    else:
        return query


def compile_typeref(expr: irast.TypeRef) -> pgast.BaseExpr:
    if expr.collection:
        raise NotImplementedError()
    else:
        result = pgast.TypeCast(
            arg=pgast.StringConstant(val=str(expr.id)),
            type_name=pgast.TypeName(
                name=('uuid',)
            )
        )

    return result


def maybe_unpack_row(expr: pgast.Base) -> Sequence[pgast.BaseExpr]:
    assert isinstance(expr, pgast.BaseExpr)
    match expr:
        case pgast.ImplicitRowExpr():
            return expr.args
        case pgast.RowExpr():
            return expr.args
    return (expr,)


def edgedb_func(
    name: str,
    *,
    ctx: context.CompilerContextLevel
) -> tuple[str, ...]:
    return common.maybe_versioned_name(
        ('edgedb', name),
        versioned=ctx.env.versioned_stdlib,
    )
