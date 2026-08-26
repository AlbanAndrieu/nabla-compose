# SonarQube

SonarQube reuses the existing PostgreSQL service instead of starting another
database.

Create a dedicated database/user, then provide `SONAR_JDBC_PASSWORD`. The
default JDBC URL is:

```text
jdbc:postgresql://172.17.0.24:5432/sonarqube
```

The TrueNAS host also needs the kernel limits required by SonarQube, notably
`vm.max_map_count`.
