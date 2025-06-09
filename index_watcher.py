from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from embedding import load_index, add_embedding_from_file
import time
import os
import logging

# Configuração de logging
logger = logging.getLogger(__name__)

# Carrega index e textos existentes
index, textos = load_index()

class DocumentoHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.pdf', '.docx', '.epub')):
            try:
                logger.info(f"[Atualizado] {event.src_path}")
                add_embedding_from_file(index, textos, event.src_path, os.path.basename(event.src_path))
            except Exception as e:
                logger.error(f"❌ Erro ao indexar {event.src_path}: {e}")

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.pdf', '.docx', '.epub')):
            try:
                logger.info(f"[Novo arquivo] {event.src_path}")
                add_embedding_from_file(index, textos, event.src_path, os.path.basename(event.src_path))
            except Exception as e:
                logger.error(f"❌ Erro ao indexar {event.src_path}: {e}")

if __name__ == "__main__":
    path = "arquivos/"
    if not os.path.exists(path):
        os.makedirs(path)

    event_handler = DocumentoHandler()
    observer = Observer()
    observer.schedule(event_handler, path=path, recursive=False)
    observer.start()

    logger.info(f"🔍 Monitorando alterações na pasta '{path}'... Pressione Ctrl+C para encerrar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("🛑 Monitoramento encerrado.")
    observer.join()