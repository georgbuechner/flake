# Database type decisions (issue #3)

Revision `e29f7b03a641` makes the scalar corrections below. It does not redesign
range storage or select values from existing ranges.

| Field | SQL type | Decision |
| --- | --- | --- |
| `availible_procedures.days_after_start` | Integer, nullable | Definition defaults are fixed day offsets. Negative values, including the sacrifice marker `-1`, remain valid. |
| `protocol_procedures.days_after_start` | String, nullable | Preserve fixed offsets and inclusive ranges such as `0-6`. Date autofill supports both; see procedure scheduling below. |
| `protocol_watercontrol.days_after_start` | String, nullable | Preserve the existing offset range. Water-control generation still requires a single integer. |
| Procedure `duration` fields | String, nullable | Procedure durations explicitly support ranges such as `2-5`; the existing parser and random selection remain unchanged. |
| `protocol_watercontrol.duration` | String, nullable | Preserve the existing `14-20` value. Water-control generation currently requires a single integer duration. |
| Procedure `requires_medication` / `requires_virus` | Integer, nullable | These are counts, not booleans. Correct the four database declarations; preserve counts greater than one. Parse submitted count strings on both creation and editing. |
| `protocol_allowed_mice.name` | String | This identifies an animal line. Preserve its existing unique and allowance check constraints. |
| `medication.procedure` | String | This identifies a procedure by name. |

For the scheduling and count fields above, `NULL` is the single unset value.
The migration and model validators normalize empty or whitespace-only strings
and the placeholders `-`, `--`, and `---` to `NULL`. Numeric zero is a real value;
negative offsets are real values as well. Other range strings are preserved
verbatim in the retained String columns.

Unset counts impose no requirement when checking for missing medication or
viruses. Unset schedule values display as blank; an animal procedure created
from an unset protocol offset starts with an empty date. Enabled water-control
generation still needs valid, configured scalar values for its start and duration.
The migration itself only preserved ranges; procedure scheduling now interprets
them as described below.

## Procedure scheduling

Procedure start offsets accept an integer or an ascending, inclusive integer
range, including negative offsets such as `-5--3`. The single value `-1` retains
its special meaning as the sacrifice-date marker.

Assigning a subprotocol leaves the start date of a procedure with a ranged offset
empty until date autofill runs. Autofill chooses a random offset within the range
and saves a calendar date relative to the experiment start. Later autofills reuse
the saved date's offset from the previous experiment start if it still fits the
configured range; otherwise they choose again. Existing fixed offsets and the
duration selection behavior are unchanged. Surgery and water-control calculations
use the actual scheduled surgery dates.

No database migration is needed for this scheduling support. The existing range
strings and saved procedure dates provide the required information.

Medication/virus amounts, concentrations and doses remain Strings: existing
values include units, percentages and combinations. Date Strings and JSON list
storage are also unchanged. Existing allowance validation remains unchanged.

## Migration and operation

The migration checks every value destined for Integer storage before changing
data. Invalid scalars, negative counts and values outside SQLite's signed 64-bit
integer range stop the migration rather than being silently cast or truncated.
It only normalizes the listed schedule/count fields and rebuilds the four tables
whose column types change. Legacy tables and extra columns are preserved.

The inspected local database contained 34 definition procedures, 776 protocol
procedures and 94 water-control configurations. Their start offsets included
14 blanks/placeholders and nine ranges. All ranges are retained by this change.
The range-bearing protocol procedure rows include references from existing
animal procedures, so automatically choosing an endpoint would change meaning.

Stop the application, back up the intended database and rehearse the upgrade on
a copy before applying it. The revision is intentionally not downgradable:
casting names back to Integer would destroy text, and the original placeholder
spellings cannot be reconstructed. Restore the pre-upgrade backup for rollback.

Database path alignment is a separate deployment concern: Alembic and the backup
code target repository `instance/larkum.db`, while the current Flask-SQLAlchemy
configuration resolves the application database under `src/instance/`. Verify
the application's actual database path and explicitly set `FLAKE_DATABASE_URL`
for migrations. This revision does not change application or backup paths.
