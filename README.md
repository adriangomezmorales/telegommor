# Herramienta de Análisis Forense para Telegram

Esta herramienta genera un reporte forense en PDF a partir de la base de datos `cache4.db` de Telegram, extrayendo y analizando mensajes, contactos y patrones de actividad.

## Características principales
- Extracción y decodificación de mensajes de Telegram
- Agrupación de conversaciones por contacto y fecha
- Análisis de patrones de actividad (horarios de uso)

## Requisitos del sistema
- Python 3.11.2 (No probado con otras versiones)
- Dependencias especificadas en `requirements.txt`

## Instalación usando entorno virtual

1. **Clonar el repositorio:**
```bash
git clone https://github.com/adriangomezmorales/telegommor
cd telegram-forensic
```
2. **Crear entorno virtual:**

```bash

python -m venv venv
```
3. **Activar el entorno virtual:**

```bash

source bin/activate
```
4. **Instalar dependencias:**

```bash

pip install -r requirements.txt
```
## Uso

```bash

python telegommor.py <ruta-al-cache4.db> [--output <nombre-archivo.pdf>]
```
