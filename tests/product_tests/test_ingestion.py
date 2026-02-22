import pytest
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.ingestion import DatasheetIngestor

@pytest.mark.asyncio
async def test_ingest_pdf():
    # Arrange
    mock_vsm = MagicMock()
    ingestor = DatasheetIngestor(vector_store_manager=mock_vsm)

    mock_doc = MagicMock()
    mock_doc.page_content = "Sample datasheet content"
    mock_doc.metadata = {"source": "test.pdf"}

    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as mock_loader_cls, \
         patch("product.bsp_agent.core.ingestion.os.path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_loader = mock_loader_cls.return_value
        mock_loader.load_and_split.return_value = [mock_doc]

        # Act
        num_chunks = await ingestor.ingest_pdf("test.pdf")

        # Assert
        assert num_chunks == 1
        mock_vsm.add_texts.assert_called_once()
        args, kwargs = mock_vsm.add_texts.call_args
        assert args[0] == ["Sample datasheet content"]
        assert args[1] == [{"source": "test.pdf"}]
