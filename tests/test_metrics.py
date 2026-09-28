from app import metrics


def test_process_metrics_collect_cpu_memory_and_rss():
    metrics.update_process_resources()
    assert metrics.REGISTRY.get_sample_value("concierge_app_process_cpu_percent") is not None
    assert metrics.REGISTRY.get_sample_value("concierge_app_process_memory_percent") is not None
    assert (metrics.REGISTRY.get_sample_value("concierge_app_process_memory_bytes") or 0) > 0
