import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = 'http://shop-api';

export const options = {
  vus: 10,
  duration: '5m',
};

export default function () {
  const payload = JSON.stringify({
    item: `load-test-${__VU}-${__ITER}`,
    quantity: 1,
  });

  const response = http.post(`${BASE_URL}/order`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(response, {
    'order created (201)': (r) => r.status === 201,
  });

  sleep(1);
}