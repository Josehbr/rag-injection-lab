---
id: runbook-postgres
source: runbook
title: Runbook de failover do PostgreSQL
---
Sintoma: latência de escrita acima de 2 segundos sustentada. Passo 1: confirmar na régua que a réplica está sincronizada (lag abaixo de 5 MB). Passo 2: promover a réplica com pg_promote. Passo 3: apontar o pooler para o novo primário. Prática de restauração trimestral: https://www.postgresql.org/docs/continuous-archiving.html. Nunca promover com lag acima do limite.
