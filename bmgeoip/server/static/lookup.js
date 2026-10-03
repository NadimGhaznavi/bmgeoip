"use strict";

const lookupForm = document.getElementById('ip-lookup');
lookupForm.addEventListener('submit', async event => {
  event.preventDefault();
  const input = document.getElementById('lookup-ip');
  const button = lookupForm.querySelector('button');
  const status = document.getElementById('lookup-status');
  const results = document.getElementById('lookup-results');
  const query = new URLSearchParams({ ip: input.value.trim() });
  input.disabled = button.disabled = true;
  status.textContent = 'Looking up IP address…';
  results.textContent = 'Waiting for lookup response…';
  try {
    const response = await fetch(`/api/lookup?${query}`, { signal: AbortSignal.timeout(30000) });
    const result = await response.json();
    results.textContent = JSON.stringify(result, null, 2);
    if (!response.ok) throw new Error(result.error || 'Could not look up this address.');
    status.textContent = result.results.length
      ? `${result.results.length} matching record(s) for ${result.ip}.`
      : `No matching records for ${result.ip}.`;
  } catch (error) {
    status.textContent = error.name === 'TimeoutError'
      ? 'Lookup timed out. Please retry.'
      : error.message || 'Could not complete the lookup.';
    if (results.textContent === 'Waiting for lookup response…') {
      results.textContent = 'No response received.';
    }
  } finally {
    input.disabled = button.disabled = false;
  }
});
