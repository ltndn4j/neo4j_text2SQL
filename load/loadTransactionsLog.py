import csv
import re
from pathlib import Path
import neo4j
from dotenv import load_dotenv

load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent
TRANSACTION_LOG_CSV = ROOT / "data" / "transactionLog.csv"

# schema.table [AS] alias — optional AS
_FROM_OR_JOIN = re.compile(
    r"\b(?:FROM|(?:INNER\s+|LEFT\s+(?:OUTER\s+)?|RIGHT\s+(?:OUTER\s+)?|"
    r"FULL\s+(?:OUTER\s+)?|CROSS\s+)?JOIN)\s+"
    r"([\w.]+)\s+(?:AS\s+)?(\w+)\b",
    re.IGNORECASE,
)
# Equality between qualified columns: a.col = b.col
_EQ_COL = re.compile(r"\b(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\b", re.IGNORECASE)


def _normalize_sql(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _build_alias_to_table(sql: str) -> dict[str, str]:
    """Map SQL alias -> bare table name (last segment of schema.table)."""
    aliases: dict[str, str] = {}
    for m in _FROM_OR_JOIN.finditer(sql):
        fq = m.group(1)
        alias = m.group(2)
        # Skip if "alias" is actually a SQL keyword (e.g. malformed)
        if alias.upper() in {"ON", "WHERE", "GROUP", "ORDER", "JOIN", "AS"}:
            continue
        table = fq.split(".")[-1]
        aliases[alias] = table
    return aliases


def _on_clause_end(s: str, start: int) -> int:
    """End index of ON ... at paren depth 0 (before WHERE / next JOIN / etc.)."""
    depth = 0
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            rest = s[i:]
            if re.match(
                r"\s+(?:WHERE|GROUP|ORDER|HAVING|LIMIT)\b",
                rest,
                re.IGNORECASE,
            ):
                return i
            if re.match(
                r"\s+(?:(?:LEFT|RIGHT|INNER|FULL|CROSS)\s+)+JOIN\b",
                rest,
                re.IGNORECASE,
            ):
                return i
        i += 1
    return n


def extract_join_column_pairs(sql: str) -> list[tuple[str, str, str, str]]:
    """
    From a SELECT-style SQL string, return unique (table_a, col_a, table_b, col_b)
    for each a.col = b.col found inside ON clauses (resolved via aliases).
    """
    sql = _normalize_sql(sql)
    aliases = _build_alias_to_table(sql)
    pairs: set[tuple[str, str, str, str]] = set()

    i = 0
    while True:
        m = re.search(r"\bON\s+", sql[i:], re.IGNORECASE)
        if not m:
            break
        on_start = i + m.end()
        on_end = _on_clause_end(sql, on_start)
        on_sql = sql[on_start:on_end]
        for em in _EQ_COL.finditer(on_sql):
            a1, c1, a2, c2 = em.group(1), em.group(2), em.group(3), em.group(4)
            t1 = aliases.get(a1)
            t2 = aliases.get(a2)
            if not t1 or not t2:
                continue
            # Canonical undirected pair -> one directed REFERENCES for MERGE idempotency
            side_a = (t1, c1)
            side_b = (t2, c2)
            lo, hi = sorted((side_a, side_b))
            pairs.add((lo[0], lo[1], hi[0], hi[1]))
        i = on_end

    return sorted(pairs)


def iter_statement_sqls(csv_path: Path):
    """Yield SQL strings embedded in PostgreSQL log CSV (statement: ...)."""
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            for field in row:
                if not isinstance(field, str) or "statement:" not in field:
                    continue
                idx = field.find("statement:")
                if idx < 0:
                    continue
                rest = field[idx + len("statement:") :].strip()
                if not rest.upper().startswith("SELECT"):
                    continue
                # Strip trailing semicolon inside the quoted log message
                rest = rest.rstrip().rstrip(";").strip()
                yield rest


def merge_references(driver: neo4j.Driver, pairs: list[tuple[str, str, str, str]]) -> None:
    cypher = """
    MERGE (c1:Column {tableName: $t1, name: $col1})
    MERGE (c2:Column {tableName: $t2, name: $col2})
    WITH c1, c2
    WHERE NOT (c1)--(:ForeignKey)--(c2)
    MERGE (c1)-[:REFERENCES]->(c2)
    """
    with driver.session() as session:
        for t1, col1, t2, col2 in pairs:
            session.run(cypher, {"t1": t1, "col1": col1, "t2": t2, "col2": col2})


def load(driver: neo4j.GraphDatabase.driver, initialize: bool = False):
    print("Analyzing users behavior in Database transactions log to enrich possible joins in the semantic layer....")
    if not TRANSACTION_LOG_CSV.is_file():
        raise FileNotFoundError(f"Missing CSV: {TRANSACTION_LOG_CSV}")

    all_pairs: set[tuple[str, str, str, str]] = set()
    for sql in iter_statement_sqls(TRANSACTION_LOG_CSV):
        for p in extract_join_column_pairs(sql):
            all_pairs.add(p)

    merge_references(driver, sorted(all_pairs))