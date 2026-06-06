# Test Report — neevai-sdk-python

Generated: 2026-06-06 14:08:20

## Summary

| Result      | Count |
|-------------|------:|
| **Total**   | 36 |
| **Passed**  | 36 |
| **Failed**  | 0 |
| **Errors**  | 0 |
| **Skipped** | 0 |
| **Time**    | 1.774s |

## Test Details

| # | Test Case | Status | Time (s) |
|---|-----------|--------|---------:|
| 1 | tests.test_client::test_client_initialization_requires_api_key | ✅ PASSED | 0.003 |
| 2 | tests.test_client::test_async_client_initialization_requires_api_key | ✅ PASSED | 0.009 |
| 3 | tests.test_errors::test_error_from_status_mapping[400-BadRequestError] | ✅ PASSED | 0.003 |
| 4 | tests.test_errors::test_error_from_status_mapping[401-AuthenticationError] | ✅ PASSED | 0.002 |
| 5 | tests.test_errors::test_error_from_status_mapping[403-PermissionDeniedError] | ✅ PASSED | 0.003 |
| 6 | tests.test_errors::test_error_from_status_mapping[404-NotFoundError] | ✅ PASSED | 0.003 |
| 7 | tests.test_errors::test_error_from_status_mapping[409-ConflictError] | ✅ PASSED | 0.002 |
| 8 | tests.test_errors::test_error_from_status_mapping[412-PreconditionFailedError] | ✅ PASSED | 0.003 |
| 9 | tests.test_errors::test_error_from_status_mapping[429-RateLimitError] | ✅ PASSED | 0.002 |
| 10 | tests.test_errors::test_error_from_status_mapping[504-DeadlineExceededError] | ✅ PASSED | 0.003 |
| 11 | tests.test_errors::test_error_from_status_mapping[500-InternalServerError] | ✅ PASSED | 0.002 |
| 12 | tests.test_errors::test_error_from_status_mapping[502-InternalServerError] | ✅ PASSED | 0.005 |
| 13 | tests.test_sandbox::test_sandbox_properties | ✅ PASSED | 0.012 |
| 14 | tests.test_sandbox::test_wait_until_ready_ready_phase | ✅ PASSED | 0.002 |
| 15 | tests.test_sandbox::test_wait_until_ready_paused_raises | ✅ PASSED | 0.002 |
| 16 | tests.test_sandbox::test_sandbox_refresh | ✅ PASSED | 0.008 |
| 17 | tests.test_sandboxd::test_dataplane_transport_sanity | ✅ PASSED | 0.005 |
| 18 | tests.test_sandboxd::test_dataplane_transport_timeout | ✅ PASSED | 0.003 |
| 19 | tests.test_sandboxd::test_dataplane_transport_connection_error | ✅ PASSED | 0.003 |
| 20 | tests.test_sandboxd::test_sandbox_connection_init | ✅ PASSED | 0.213 |
| 21 | tests.test_sandboxd::test_async_sandbox_connection_init | ✅ PASSED | 0.040 |
| 22 | tests.test_sandboxd::test_sandbox_connection_close_idempotent | ✅ PASSED | 0.030 |
| 23 | tests.test_sandboxes::test_sandboxes_create | ✅ PASSED | 0.003 |
| 24 | tests.test_sandboxes::test_sandboxes_get | ✅ PASSED | 0.003 |
| 25 | tests.test_sandboxes::test_sandboxes_list | ✅ PASSED | 0.003 |
| 26 | tests.test_sandboxes::test_sandboxes_delete | ✅ PASSED | 0.003 |
| 27 | tests.test_sandboxes::test_sandboxes_pause_resume | ✅ PASSED | 0.002 |
| 28 | tests.test_sandboxes::test_sandboxes_metrics | ✅ PASSED | 0.003 |
| 29 | tests.test_sandboxes::test_sandboxes_get_not_found | ✅ PASSED | 0.002 |
| 30 | tests.test_transport::test_calculate_backoff_values | ✅ PASSED | 0.001 |
| 31 | tests.test_transport::test_parse_retry_after_seconds | ✅ PASSED | 0.001 |
| 32 | tests.test_transport::test_parse_retry_after_http_date | ✅ PASSED | 0.001 |
| 33 | tests.test_transport::test_control_transport_retries | ✅ PASSED | 1.002 |
| 34 | tests.test_transport::test_control_transport_timeout | ✅ PASSED | 0.001 |
| 35 | tests.test_transport::test_control_transport_connection_error | ✅ PASSED | 0.001 |
| 36 | tests.test_transport::test_control_transport_sanity | ✅ PASSED | 0.002 |

---
*Report generated from JUnit XML output.*
