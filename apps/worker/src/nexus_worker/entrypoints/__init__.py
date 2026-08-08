"""Worker service entrypoints (WP-07).

One module per service of the v2 map: ``runner`` (scales by queue lag),
``scheduler`` (singleton; WP-08 advisory locks make 2 replicas safe during
rollout), ``egress`` (scales by pending outbound). ``nexus_worker.main``
remains the all-in-one dev/rollback mode.
"""
