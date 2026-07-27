import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.patients import _build_asr_integrity


def test_empty_asr_segment_is_processed_not_missing():
    integrity = _build_asr_integrity(
        {
            "status": "success",
            "segments": [
                {"seg_index": 1, "text": ""},
                {"seg_index": 2, "text": "内膜16.7，右侧未见明显卵泡"},
                {"seg_index": 3, "text": "左卵巢大小25乘以24"},
            ],
            "full_transcript": "内膜16.7，右侧未见明显卵泡\n左卵巢大小25乘以24",
            "config_snapshot": {"params": {"audio_input_mode": "segments"}},
        },
        3,
    )

    assert integrity["missing_segment_indices"] == []
    assert integrity["empty_segment_indices"] == [1]
    assert integrity["level"] == "complete_with_empty"
