"""Build the DataSources listed in config/rag.yaml."""

from core.interfaces.data_source import DataSource
from core.rag_config import RagConfig
from ingestion.sources.markdown_dir import AcmeDocsSource, GitLabHandbookSource

SOURCE_KINDS: dict[str, type[GitLabHandbookSource | AcmeDocsSource]] = {
    "gitlab_handbook": GitLabHandbookSource,
    "acme_docs": AcmeDocsSource,
}


def build_sources(config: RagConfig) -> list[DataSource]:
    return [SOURCE_KINDS[s.kind](s.directory, name=s.name) for s in config.sources]
