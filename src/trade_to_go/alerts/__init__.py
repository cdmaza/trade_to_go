"""Alerting: state machine (fire on state change only), dedupe, formatter, scorer.

Every alert is written to ops.sqlite alert_log and scored at 5, 20 and 60 days
against the benchmark in config/alerts.yaml.
"""
