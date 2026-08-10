# Penpot visual verification

Verified on 2026-08-10 against the connected Penpot file
`81f57451-85cc-819d-8008-6fe553a2574d`.

## References

- Desktop board: `46abee9f-97c0-80ce-8008-6ff3f10e4923`, 1440 × 1024
- Component and state board: `46abee9f-97c0-80ce-8008-6ff26a5df0e6`, 1240 × 1024

Both boards were exported as PNG and visually inspected. The implementation was
checked in the initial, streaming, completed research, completed knowledge,
failure, cancellation, and variable-length answer states.

## Comparison results

| Area                 | Penpot reference                                                                   | Implementation result                                                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Shell                | 72 px top bar, 224 px sidebar                                                      | Matches CSS tokens and grid dimensions                                                                                                 |
| Main content         | 1120 px maximum width, 48 px right/left content inset at 1440 px                   | Matches `--content-max-width` and fluid content padding                                                                                |
| Workspace            | Starts at x=272/y=200 and reaches approximately y=959                              | Width and origin match; viewport-relative minimum height now preserves the reference depth at 1440 × 1024                              |
| Composer             | 76 px inset from workspace content edge, 112 px nominal height, 48 px send control | Matches composer spacing and sizing tokens                                                                                             |
| Semantic states      | Blue fact, green analysis, red risk, muted source metadata                         | Matches the verified token palette and section hierarchy                                                                               |
| Unsupported controls | Reference shows future navigation, search, identity, and attachment affordances    | Future navigation is visibly disabled; search, identity, notifications, and attachment are omitted so MVP functionality is not implied |
| Variable content     | Answer rows expand vertically                                                      | Workspace remains auto-height and long question, answer, and citation text wraps without horizontal clipping                           |

The unsupported-control differences are intentional product-scope adaptations
required by the MVP specification, rather than visual regressions.
