import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://shop-api';

export const options = {
  scenarios: {
    order_load: {
      executor: 'constant-arrival-rate',
      rate: 5,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 5,
      maxVUs: 20,
    },
  },

  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.05'],
    checks: ['rate>0.95'],
  },
};

export default function () {
  const payload = JSON.stringify({
    item: `load-test-${__VU}-${__ITER}`,
    quantity: 1,
  });

  const response = http.post(`${BASE_URL}/order`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'create-order' },
  });

  check(response, {
    'order created (201)': (r) => r.status === 201,
  });
}