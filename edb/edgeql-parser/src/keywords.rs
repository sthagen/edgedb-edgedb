pub const UNRESERVED_KEYWORDS: &[&str] = &[
    "abort",
    "abstract",
    "access",
    "after",
    "alias",
    "allow",
    "all",
    "annotation",
    "applied",
    "as",
    "asc",
    "assignment",
    "before",
    "cardinality",
    "cast",
    "committed",
    "config",
    "conflict",
    "constraint",
    "cube",
    "current",
    "database",
    "ddl",
    "declare",
    "default",
    "deferrable",
    "deferred",
    "delegated",
    "desc",
    "deny",
    "each",
    "empty",
    "expression",
    "extension",
    "final",
    "first",
    "from",
    "function",
    "future",
    "implicit",
    "index",
    "infix",
    "inheritable",
    "instance",
    "into",
    "isolation",
    "json",
    "last",
    "link",
    "migration",
    "multi",
    "named",
    "object",
    "of",
    "only",
    "onto",
    "operator",
    "optionality",
    "order",
    "orphan",
    "overloaded",
    "owned",
    "package",
    "policy",
    "populate",
    "postfix",
    "prefix",
    "property",
    "proposed",
    "pseudo",
    "read",
    "reject",
    "release",
    "rename",
    "required",
    "reset",
    "restrict",
    "rewrite",
    "role",
    "roles",
    "rollup",
    "savepoint",
    "scalar",
    "schema",
    "sdl",
    "serializable",
    "session",
    "source",
    "superuser",
    "system",
    "target",
    "ternary",
    "text",
    "then",
    "to",
    "transaction",
    "trigger",
    "type",
    "unless",
    "using",
    "verbose",
    "version",
    "view",
    "write",
];


pub const PARTIAL_RESERVED_KEYWORDS: &[&str] = &[
    // Keep in sync with `tokenizer::is_keyword`
    "except",
    "intersect",
    "union",
    // Keep in sync with `tokenizer::is_keyword`
];


pub const FUTURE_RESERVED_KEYWORDS: &[&str] = &[
    // Keep in sync with `tokenizer::is_keyword`
    "anyarray",
    "begin",
    "case",
    "check",
    "deallocate",
    "discard",
    "end",
    "explain",
    "fetch",
    "get",
    "global",
    "grant",
    "import",
    "listen",
    "load",
    "lock",
    "match",
    "move",
    "notify",
    "on",
    "over",
    "prepare",
    "partition",
    "raise",
    "refresh",
    "reindex",
    "revoke",
    "single",
    "when",
    "window",
    "never",
    // Keep in sync with `tokenizer::is_keyword`
];

pub const CURRENT_RESERVED_KEYWORDS: &[&str] = &[
    // Keep in sync with `tokenizer::is_keyword`
    "__source__",
    "__subject__",
    "__type__",
    "__std__",
    "__edgedbsys__",
    "__edgedbtpl__",
    "__std__",
    "__new__",
    "__old__",
    "__specified__",
    "administer",
    "alter",
    "analyze",
    "and",
    "anytuple",
    "anytype",
    "by",
    "commit",
    "configure",
    "create",
    "delete",
    "describe",
    "detached",
    "distinct",
    "do",
    "drop",
    "else",
    "exists",
    "extending",
    "false",
    "filter",
    "for",
    "group",
    "if",
    "ilike",
    "in",
    "insert",
    "introspect",
    "is",
    "like",
    "limit",
    "module",
    "not",
    "offset",
    "optional",
    "or",
    "rollback",
    "select",
    "set",
    "start",
    "true",
    "typeof",
    "update",
    "variadic",
    "with",
    // Keep in sync with `tokenizer::is_keyword`
];
