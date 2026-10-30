"""Build the DataSources listed in config/rag.yaml."""

from core.interfaces.data_source import DataSource
from core.rag_config import RagConfig
from ingestion.sources.markdown_dir import AcmeDocsSource, GitLabHandbookSource
from ingestion.sources.uploads import UploadSource


def build_sources(config: RagConfig) -> list[DataSource]:
    sources: list[DataSource] = []
    for s in config.sources:
        match s.kind:
            case "gitlab_handbook":
                sources.append(GitLabHandbookSource(s.directory, name=s.name))
            case "acme_docs":
                sources.append(AcmeDocsSource(s.directory, name=s.name))
            case "uploads":
                sources.append(UploadSource(s.directory, config.uploads.extensions, s.name))
    return sources
