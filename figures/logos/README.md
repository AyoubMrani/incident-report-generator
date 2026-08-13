# Technology logos

Drop vector logo files here with these exact names (PDF or PNG, transparent
background preferred). The report's `\techlogo{figures/logos/<name>}{Label}`
calls reference them by this path; if a file is missing, a bracketed
placeholder renders instead so the layout still compiles.

| Filename            | Technology         |
|---------------------|---------------------|
| postgresql.pdf       | PostgreSQL          |
| minio.pdf             | MinIO                |
| keycloak.pdf           | Keycloak              |
| pgvector.pdf            | pgvector (optional — often just the PostgreSQL mark) |
| react.pdf                | React                  |
| fastapi.pdf                | FastAPI                 |
| docker.pdf                    | Docker                    |
| tailwindcss.pdf                 | Tailwind CSS               |

Official logo/brand assets are usually available from each project's press
kit or `/brand` page (e.g. postgresql.org, min.io, keycloak.org). Vector
(SVG/PDF) is strongly preferred over PNG so the row stays crisp at print
resolution — the same reason the architecture diagrams in `figures/` are
SVG-sourced.

PNG works too: `\techlogo` takes whatever `\includegraphics` accepts.
