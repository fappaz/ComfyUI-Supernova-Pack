from supernova.core.workflow import used_outputs

PROMPT = {
    "1": {"class_type": "LoadAudio", "inputs": {"audio": "song.mp3"}},
    "2": {"class_type": "SupernovaGenerateAudioSpectrogram", "inputs": {"audio": ["1", 0], "width": 640}},
    "3": {"class_type": "SaveVideo", "inputs": {"video": ["2", 2]}},
    "4": {"class_type": "PreviewImage", "inputs": {"images": ["2", 0]}},
}


def test_used_outputs():
    assert used_outputs(PROMPT, "2") == {0, 2}
    assert used_outputs(PROMPT, 2) == {0, 2}
    assert used_outputs(PROMPT, "1") == {0}
    assert used_outputs(PROMPT, "4") == set()


def test_used_outputs_unknown():
    assert used_outputs(None, "2") is None
    assert used_outputs(PROMPT, None) is None
