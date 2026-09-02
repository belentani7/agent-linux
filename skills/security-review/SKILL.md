---
name: security-review
description: Revisa cambios de código y configuración buscando secretos, permisos excesivos y dependencias riesgosas.
---

# Security review

- Busca secretos con `git diff --check` y revisa patrones de claves sin mostrar su valor.
- Comprueba que `.env`, claves SSH y credenciales estén ignorados.
- Examina scripts remotos, permisos sudo, puertos expuestos y servicios persistentes.
- Prefiere documentación oficial y versiones fijadas cuando sea una build reproducible.
- Reporta hallazgos por severidad: crítico, alto, medio o bajo; incluye mitigación.
