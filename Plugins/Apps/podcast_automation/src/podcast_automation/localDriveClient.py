from .settings import get_download_dir
import shutil
from datetime import datetime, timezone
from pathlib import Path


class LocalDriveClient:
    def __init__(self):
        pass

    def list_zip_files(self, folder_path: str) -> list[dict]:
        """Lista todos os arquivos ZIP localizados no diretório informado."""
        files: list[dict] = []

        folder = Path(folder_path)
        if folder.is_dir():
            for arquivo in folder.iterdir():
                if arquivo.is_file() and arquivo.suffix.lower() == ".zip":
                    files.append(
                        {
                            "id": str(arquivo),
                            "path": str(arquivo),
                            "name": arquivo.name,
                            "size": arquivo.stat().st_size,
                            "createdTime": datetime.fromtimestamp(
                                arquivo.stat().st_ctime,
                                tz=timezone.utc,
                            ).isoformat(),
                            "modifiedTime": datetime.fromtimestamp(
                                arquivo.stat().st_mtime,
                                tz=timezone.utc,
                            ).isoformat(),
                        }
                    )

        files.sort(key=lambda x: x["createdTime"])
        return files

    def download_file(self, file: dict) -> Path:
        """
        Copia um arquivo local para a pasta 'download',
        localizada ao lado do programa, e retorna o caminho do arquivo.
        """

        download_dir = get_download_dir()

        source = Path(file["path"])
        destination = download_dir / file["name"]

        if destination.exists():
            print(f"Pulando {file['name']} já copiado")
            return destination

        shutil.copy2(source, destination)

        return destination

    def rename_processed(self, id: str, name: str, status: str = "ok") -> None:
        source = Path(id)

        suffix = f"-{status}"

        if name.lower().endswith(f"{suffix}.zip"):
            print(f"Local: {name} já estava marcado como processado ({status})")
            return

        if name.lower().endswith(".zip"):
            new_name = name[:-4] + f"{suffix}.zip"
        else:
            new_name = name + suffix

        destination = source.with_name(new_name)
        source.rename(destination)

        print(f"Local: arquivo marcado como processado: {new_name}")
