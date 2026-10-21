---
id: gh-issue-911
source: github
title: Issue 911 sobre rate limiting da API pública
---
Issue 911 relata que a API pública devolve 429 antes do limite contratado para dois clientes do plano Pro. Suspeita inicial: contagem por IP atrás do CDN contando o mesmo cliente duas vezes. Etiquetas: bug, prioridade alta. Documentação oficial citada no debate: https://datatracker.ietf.org/doc/html/rfc6585.
