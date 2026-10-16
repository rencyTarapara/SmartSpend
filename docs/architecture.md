

\# SmartSpend Architecture



\## Frontend

HTML, CSS and JavaScript provide the user interface.



\## Expense Service

Manages income and expense transactions through REST APIs.



\## Budget Service

Creates budgets and calculates budget utilization.



\## Analytics Service

Calculates monthly summaries and category-wise spending.



\## Alert Service

Generates notifications when spending exceeds configured thresholds.



\## Database

SQLite stores application data during initial development.



\## Containerization

Docker packages each backend service. Docker Compose runs the services locally.



\## CI/CD

GitHub Actions runs tests, security checks and Docker image builds.



\## Infrastructure

Terraform describes the resources needed for the selected deployment environment.



\## Security

Bandit, pip-audit and Trivy check code, dependencies and container images.



