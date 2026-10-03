"use strict";

async function updateDataProgress() {
  const progress = document.getElementById('data-progress');
  const status = document.getElementById('data-status');
  try {
    const response = await fetch('/api/data-status', { signal: AbortSignal.timeout(10000) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    progress.hidden = ['ready', 'error'].includes(result.phase);
    if (result.total > 0) {
      progress.max = result.total;
      progress.value = result.completed;
    } else {
      progress.removeAttribute('value');
    }
    const family = result.version ? `IPv${result.version}: ` : '';
    const unit = result.phase === 'downloading' ? ' bytes' : ' records';
    const count = result.completed ? ` · ${result.completed.toLocaleString()}${unit}` : '';
    status.textContent = result.message || `${family}${result.phase}${count}`;
  } catch (error) {
    status.textContent = 'Could not read dataset progress. Retrying…';
  } finally {
    setTimeout(updateDataProgress, 2000);
  }
}
updateDataProgress();

const form = document.getElementById('download-schedule');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const enabled = document.getElementById('schedule-enabled');
  const expression = document.getElementById('schedule-expression');
  const status = document.getElementById('schedule-status');
  button.disabled = enabled.disabled = expression.disabled = true;
  status.textContent = 'Saving schedule…';
  try {
    const response = await fetch('/api/download-schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enabled.checked, expression: expression.value }),
      signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not save the schedule.');
    enabled.checked = result.schedule.enabled;
    expression.value = result.schedule.expression;
    status.textContent = result.schedule.enabled ? 'Schedule saved. Scheduled downloads enabled.' : 'Schedule saved. Scheduled downloads disabled.';
  } catch (error) {
    status.textContent = error.name === 'TimeoutError'
      ? 'The save request timed out. Reload to check the saved schedule before retrying.'
      : error.message || 'Could not save the schedule.';
  } finally {
    button.disabled = enabled.disabled = expression.disabled = false;
  }
});
