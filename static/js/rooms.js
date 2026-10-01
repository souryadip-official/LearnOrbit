(() => {
  const config = window.studyRoomsConfig;
  if (!config) return;

  const feedback = document.getElementById('rooms-feedback');
  const list = document.getElementById('message-list');
  const empty = document.getElementById('message-empty');
  const active = document.getElementById('chat-active');
  const placeholder = document.getElementById('chat-placeholder');
  const roomName = document.getElementById('active-room-name');
  const inviteShare = document.getElementById('invite-share');
  const inviteCode = document.getElementById('active-invite-code');
  const messageForm = document.getElementById('message-form');
  const leaveButton = document.getElementById('leave-room');
  let selectedRoom = null;
  let latestId = 0;
  let pollTimer = null;
  let pollInFlight = false;
  document.addEventListener('learnorbit:beforepagechange', () => clearInterval(pollTimer), {once: true});

  const setFeedback = (message, kind = '') => {
    feedback.textContent = message || '';
    feedback.dataset.kind = kind;
  };

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        'X-CSRFToken': config.csrfToken,
        ...(options.body ? {'Content-Type': 'application/json'} : {}),
        ...options.headers,
      },
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(response.status === 400
        ? 'Security token expired or missing. Refresh the page and try again.'
        : 'The server returned an unexpected response.');
    }
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    return data;
  }

  function appendMessage(message) {
    const node = document.createElement('article');
    node.className = `room-message${message.username === config.currentUsername ? ' is-mine' : ''}`;
    const meta = document.createElement('div');
    meta.className = 'room-message-meta';
    const author = document.createElement('strong');
    author.textContent = message.username;
    const time = document.createElement('time');
    const date = new Date(message.created_at);
    time.dateTime = message.created_at;
    time.textContent = Number.isNaN(date.getTime())
      ? ''
      : date.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'});
    const body = document.createElement('p');
    body.textContent = message.text;
    meta.append(author, time);
    node.append(meta, body);
    list.append(node);
    empty.hidden = true;
  }

  async function pollMessages() {
    if (!selectedRoom || pollInFlight) return;
    pollInFlight = true;
    const room = selectedRoom;
    try {
      const template = config.messagesUrlTemplate.replace(/0(?=\/messages(?:\?|$))/, String(room.id));
      const data = await requestJson(`${template}?after=${latestId}`);
      if (selectedRoom?.id !== room.id) return;
      room.isOwner = data.is_owner;
      inviteShare.hidden = !room.isOwner;
      inviteCode.textContent = room.isOwner ? room.inviteCode : '';
      data.messages.forEach(appendMessage);
      latestId = data.next_after;
      if (data.messages.length) list.scrollTop = list.scrollHeight;
    } catch (error) {
      setFeedback(error.message, 'error');
      if (/not a member|not found/i.test(error.message)) {
        clearInterval(pollTimer);
        selectedRoom = null;
        active.hidden = true;
        placeholder.hidden = false;
      }
    } finally {
      pollInFlight = false;
    }
  }

  function selectRoom(room) {
    selectedRoom = room;
    latestId = 0;
    list.querySelectorAll('.room-message').forEach(node => node.remove());
    empty.hidden = false;
    roomName.textContent = room.name;
    placeholder.hidden = true;
    active.hidden = false;
    inviteShare.hidden = !room.isOwner;
    inviteCode.textContent = room.isOwner ? room.inviteCode : '';
    document.querySelectorAll('.room-choice').forEach(button => {
      button.setAttribute('aria-current', Number(button.dataset.roomId) === room.id ? 'true' : 'false');
    });
    setFeedback('');
    clearInterval(pollTimer);
    pollMessages();
    pollTimer = setInterval(pollMessages, 3000);
  }

  document.querySelectorAll('.room-choice').forEach(button => {
    button.addEventListener('click', () => {
      const room = config.rooms.find(item => item.id === Number(button.dataset.roomId));
      if (room) selectRoom(room);
    });
  });

  document.getElementById('create-room-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const name = new FormData(form).get('name');
    try {
      const data = await requestJson(config.createUrl, {
        method: 'POST',
        body: JSON.stringify({name}),
      });
      sessionStorage.setItem('studyRoomsNotice', `Room created. Share invite code ${data.room.invite_code} with your study group.`);
      location.reload();
    } catch (error) {
      setFeedback(error.message, 'error');
    }
  });

  document.getElementById('join-room-form').addEventListener('submit', async event => {
    event.preventDefault();
    const invite_code = new FormData(event.currentTarget).get('invite_code');
    try {
      await requestJson(config.joinUrl, {
        method: 'POST',
        body: JSON.stringify({invite_code}),
      });
      sessionStorage.setItem('studyRoomsNotice', 'You joined the room.');
      location.reload();
    } catch (error) {
      setFeedback(error.message, 'error');
    }
  });

  document.getElementById('copy-invite').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(inviteCode.textContent);
      setFeedback('Invite code copied.', 'success');
    } catch {
      setFeedback('Copy was unavailable. Select and copy the invite code.', 'error');
    }
  });

  leaveButton.addEventListener('click', async () => {
    if (!selectedRoom || leaveButton.disabled) return;
    const room = selectedRoom;
    const ownerNotice = room.isOwner
      ? ' As the owner, you will pass ownership to the longest-standing member; if you are the last member, the room and its messages will be deleted.'
      : '';
    if (!window.confirm(`Leave "${room.name}"?${ownerNotice}`)) return;

    leaveButton.disabled = true;
    setFeedback('Leaving the room…');
    clearInterval(pollTimer);
    try {
      const url = config.leaveUrlTemplate.replace(/0(?=\/leave(?:\?|$))/, String(room.id));
      const data = await requestJson(url, {method: 'POST', body: JSON.stringify({})});
      selectedRoom = null;
      latestId = 0;
      list.querySelectorAll('.room-message').forEach(node => node.remove());
      empty.hidden = false;
      messageForm.reset();
      active.hidden = true;
      placeholder.hidden = false;

      const roomButton = document.querySelector(`.room-choice[data-room-id="${room.id}"]`);
      roomButton?.remove();
      config.rooms = config.rooms.filter(item => item.id !== room.id);
      const count = document.querySelector('.rooms-count');
      if (count) {
        count.textContent = String(config.rooms.length);
        count.setAttribute('aria-label', `${config.rooms.length} rooms`);
      }
      if (!config.rooms.length) {
        const roomList = document.querySelector('.rooms-list');
        if (roomList) {
          const notice = document.createElement('div');
          notice.className = 'rooms-empty';
          const title = document.createElement('h3');
          title.textContent = 'Your room list is empty';
          const description = document.createElement('p');
          description.textContent = 'Create a room or join one with a code to see your study circle here.';
          notice.append(title, description);
          roomList.replaceWith(notice);
        }
      }
      setFeedback(
        data.room_deleted
          ? 'You left. The empty room and its messages were cleaned up.'
          : data.ownership_transferred
            ? 'You left and ownership passed to another member.'
            : 'You left the study room.',
        'success',
      );
    } catch (error) {
      setFeedback(error.message, 'error');
      if (selectedRoom?.id === room.id) {
        pollMessages();
        pollTimer = setInterval(pollMessages, 3000);
      }
    } finally {
      leaveButton.disabled = false;
    }
  });

  messageForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!selectedRoom) return;
    const textarea = document.getElementById('message-text');
    const text = textarea.value;
    const room = selectedRoom;
    const url = config.sendUrlTemplate.replace(/0(?=\/messages(?:\?|$))/, String(room.id));
    const submit = messageForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const data = await requestJson(url, {method: 'POST', body: JSON.stringify({text})});
      if (selectedRoom?.id !== room.id) return;
      if (data.message.id > latestId) {
        appendMessage(data.message);
        latestId = data.message.id;
        list.scrollTop = list.scrollHeight;
      }
      textarea.value = '';
      setFeedback('');
    } catch (error) {
      setFeedback(error.message, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  const notice = sessionStorage.getItem('studyRoomsNotice');
  if (notice) {
    sessionStorage.removeItem('studyRoomsNotice');
    setFeedback(notice, 'success');
  }
})();
