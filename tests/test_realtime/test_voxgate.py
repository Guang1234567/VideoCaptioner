from videocaptioner.core.realtime.voxgate import normalize_voxgate_message


def test_normalize_voxgate_delta_event():
    event = normalize_voxgate_message(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "item_000001",
            "delta": "你好",
        }
    )

    assert event is not None
    assert event.type == "delta"
    assert event.text == "你好"
    assert event.item_id == "item_000001"


def test_normalize_voxgate_completed_event():
    event = normalize_voxgate_message(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item_000001",
            "transcript": "你好，世界。",
        }
    )

    assert event is not None
    assert event.type == "completed"
    assert event.text == "你好，世界。"


def test_normalize_voxgate_error_event():
    event = normalize_voxgate_message(
        {
            "type": "error",
            "error": {"message": "bad audio"},
        }
    )

    assert event is not None
    assert event.type == "error"
    assert event.text == "bad audio"


def test_ignores_unrelated_events():
    assert normalize_voxgate_message({"type": "input_audio_buffer.committed"}) is None
