(() => {
  const box = document.getElementById('status-messages');
  const rows = document.getElementById('status-message-rows');
  const pad = value => String(value).padStart(2, '0');
  function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }
  let displayed = [];
  async function refreshStatusMessages() {
    try {
      const response = await fetch('/status-messages', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
      if (!response.ok) return;
      const messages = await response.json();
      const following = box.scrollTop + box.clientHeight >= box.scrollHeight - 1;
      // Rebuild when retained history rolls over or changes.
      if (messages.length < displayed.length || displayed.some((message, i) =>
        message.timestamp !== messages[i].timestamp ||
        message.source !== messages[i].source || message.message !== messages[i].message)) {
        rows.replaceChildren();
        displayed = [];
      }
      for (const message of messages.slice(displayed.length)) {
        const row = document.createElement('tr');
        for (const value of [formatTimestamp(message.timestamp), message.source, message.message]) {
          const cell = document.createElement('td');
          cell.textContent = value;
          row.append(cell);
        }
        rows.append(row);
      }
      displayed = messages;
      if (following) box.scrollTop = box.scrollHeight;
    } catch (error) {
      // Keep the current history visible while the server is unreachable.
    } finally {
      window.setTimeout(refreshStatusMessages, 2000);
    }
  }
  refreshStatusMessages();
})();
