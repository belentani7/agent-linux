# BELENTANI Cloud MCP — Oracle ARM64 + GPU por horas

**Estado a 2026-10-29:** prototipo integrado en `agent-linux`. No provisiona infraestructura, no instala modelos, no inicia instancias de pago ni abre acceso público. **Ejecución remota desactivada por defecto.**

## Arquitectura

PC / cliente MCP → `ssh -T` sobre Tailscale → `scripts/belentani_cloud_mcp.py` en la VM Linux → servicios locales:
- `llama.cpp` / Qwen3.5-0.8B-GGUF, solo CPU ARM64 (127.0.0.1:8080)
- ACE-Step 1.5 para generación musical, API `/release_task` y `/query_result` (127.0.0.1:8001)
- ComfyUI para workflows de vídeo, API `/prompt` y `/history/{uuid}` (127.0.0.1:8188)
- OpenVoice V2, Applio y Demucs como candidatos **sin adaptador implementado**.

La instancia GPU se alquila/arranca por separado y sus APIs se conectan a la VM a través de túneles SSH de loopback. El MCP no dispone de claves de proveedores ni capacidad de contratar GPUs. El catálogo completo está en `config/ai-stack-catalog.json`.

## Instalación en Linux (local o VM)

Requiere Python 3.12+ y un cliente MCP compatible:

```bash
python3 -m venv .venv
.venv/bin/pip install 'mcp[cli]'
python3 -m unittest discover -s tests -p 'test_belentani_cloud_core.py' -v
.venv/bin/python scripts/belentani_cloud_mcp.py
```

El proceso MCP no imprime nada: espera mensajes JSON-RPC en stdin. Para PC remoto, ajusta `config/mcp.cloud.example.json` al cliente y crea un alias SSH `oracle-mcp` que conecte por Tailscale, con clave SSH. Ejemplo de alias en tu PC:

```sshconfig
Host oracle-mcp
  HostName 100.x.y.z
  User ubuntu
  IdentityFile ~/.ssh/id_ed25519
```

**No abras los puertos 8001, 8080 ni 8188 a internet.** Si alquilas una GPU distinta:

```bash
ssh -N -L 8001:127.0.0.1:8001 usuario@gpu-host
ssh -N -L 8188:127.0.0.1:8188 usuario@gpu-host
```

Usa las instrucciones oficiales de [Tailscale](https://tailscale.com/kb/1031/install-linux) y los datos reales de tu máquina. Para LLM CPU, instala [llama.cpp](https://github.com/ggml-org/llama.cpp) en ARM64 y ejecuta `llama serve -hf ggml-org/Qwen3.5-0.8B-GGUF --host 127.0.0.1`; verifica el comando con la versión instalada.

## Modo de ejecución pagado: bloqueo inicial

`create_music` y `submit_video` hacen **dry-run** mientras `BELENTANI_GPU_SUBMIT_ENABLED` no sea `1`. Una vez levantado el backend GPU, con las tarifas reales y un máximo estimado por trabajo comprobados:

```bash
export BELENTANI_ACE_URL=http://127.0.0.1:8001
export BELENTANI_COMFY_URL=http://127.0.0.1:8188
export BELENTANI_WORKFLOW_DIR="$HOME/ai-workflows"
export BELENTANI_GPU_RATE_USD_H=0.69
export BELENTANI_GPU_MAX_ESTIMATED_USD=1.00
export BELENTANI_GPU_SUBMIT_ENABLED=1
```

Para ACE-Step autenticado, introduce `BELENTANI_ACE_API_KEY` mediante tu gestor de secretos o entorno privado, **nunca en el repositorio**. Los gráficos de ComfyUI deben estar exportados en formato API JSON y revisados previamente.

El presupuesto es una **estimación**, no un límite de facturación: no detiene ni elimina el Pod, no contabiliza los minutos de arranque, disco, redes ni impuestos. Configura límites reales con el proveedor y elimina discos persistentes cuando finalices. No confundir `Stop` con borrado de recursos.

## Seguridad y límites reales

- Todas las URLs de modelos se limitan a `localhost` / `127.0.0.1`, sin redirecciones HTTP, ni proxy del entorno.
- Archivos ComfyUI: solo basename `.json` en un directorio permitido, máximo 1 MB; revisar siempre custom nodes no confiables.
- No hay herramientas MCP para shell, `sudo`, tokens, GitHub push, contratación o destrucción de servicios.
- Voz hablada/cantada: solo la propia o la utilizada con autorización; revisar licencia de pesos y LoRA para música comercial.
- `music_status` y `video_status` consultan servidores existentes, no descargan archivos con enlaces arbitrarios.

## Recursos y licencias

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — MIT.
- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) y su [API](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md).
- [OpenVoice V2](https://github.com/myshell-ai/OpenVoice) — MIT.
- [Applio](https://github.com/IAHispano/Applio) — MIT y términos adicionales de uso.
- [Demucs](https://github.com/facebookresearch/demucs) — MIT, repositorio original archivado.
- [Wan 2.2](https://github.com/Wan-Video/Wan2.2) y [pesos 5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) — Apache 2.0.
- [ComfyUI](https://github.com/Comfy-Org/ComfyUI) — revisar por separado los nodos.
- [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm): documentación técnica indica 2 OCPU/12 GB, 1.500 OCPU-h y 9.000 GB-h/mes; información comercial inconsistente sobre 4/24, usar límite de tenancy comprobado.
- [Hugging Face ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu): alternativa de demos gratuitas con cuota; no garantiza GPU para workloads extensos.

## Validación

La suite `tests/test_belentani_cloud_core.py` pasó **9 pruebas unitarias en entorno local**, incluyendo dry-run sin red, validaciones, SSRF, estimación de precio y mock de ComfyUI. También se validó sintaxis Python y JSON. **No** se ha ejecutado una VM OCI real, ni se ha probado una GPU real, ni se ha medido calidad o coste audiovisual. No anunciar el despliegue como completado hasta entonces.
