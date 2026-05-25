(function () {
  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (char) {
      var random = (Math.random() * 16) | 0;
      var value = char === 'x' ? random : (random & 0x3) | 0x8;
      return value.toString(16);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var config = window.moduleFrameConfig || {};
    var iframe = document.getElementById('content-iframe');
    var blockedNotice = document.getElementById('iframe-blocked-notice');
    var stateNode = document.getElementById('state-data');
    var csrfNode = document.getElementById('module-frame-csrf');

    if (!iframe) {
      return;
    }

    function showBlockedNotice() {
      if (blockedNotice) {
        blockedNotice.classList.remove('hidden');
      }
      iframe.classList.add('hidden');
    }

    function getStateData() {
      if (!stateNode) {
        return null;
      }
      try {
        return JSON.parse(stateNode.textContent);
      } catch (error) {
        return null;
      }
    }

    function probeSplice() {
      if (!iframe.contentWindow) {
        return;
      }
      ['SPLICE.getState', 'SPLICE.ping', 'SPLICE.hello'].forEach(function (subject) {
        iframe.contentWindow.postMessage({ subject: subject, message_id: uuid() }, '*');
      });
    }

    iframe.addEventListener('load', function () {
      probeSplice();
      setTimeout(probeSplice, 900);
      setTimeout(probeSplice, 2400);
    });

    document.addEventListener('securitypolicyviolation', function (event) {
      if (event.violatedDirective && event.violatedDirective.indexOf('frame-ancestors') !== -1) {
        showBlockedNotice();
      }
    });

    iframe.addEventListener('error', function () {
      setTimeout(showBlockedNotice, 1400);
    });

    window.addEventListener('message', function (event) {
      var messageData = event.data;
      if (typeof messageData === 'string') {
        try {
          messageData = JSON.parse(messageData);
        } catch (error) {
          return;
        }
      }

      var allowedOrigins = new Set([
        window.location.origin,
        'https://codecheck.me',
        'https://codecheck.io',
        'https://adapt2.sis.pitt.edu',
        'https://pawscomp2.sis.pitt.edu',
        'https://columbus.exp.sis.pitt.edu',
        'https://pcrs.utm.utoronto.ca/',
        'https://acos.cs.vt.edu',
      ]);

      if (!allowedOrigins.has(event.origin)) {
        return;
      }

      if (messageData && messageData.subject === 'SPLICE.getState') {
        var state = getStateData();
        if (!state || !iframe.contentWindow) {
          return;
        }
        iframe.contentWindow.postMessage({
          subject: 'SPLICE.getState.response',
          message_id: messageData.message_id,
          state: state,
        }, event.origin);
        return;
      }

      if (messageData && messageData.subject === 'SPLICE.reportScoreAndState') {
        if (config.previewMode || !config.progressUrl) {
          return;
        }

        var progressValue = 0;
        if (messageData.state && messageData.state.scoreText && messageData.state.scoreText.indexOf('/') !== -1) {
          var parts = messageData.state.scoreText.split('/');
          var completed = parseInt(parts[0], 10);
          var total = parseInt(parts[1], 10);
          if (total > 0) {
            progressValue = (completed / total) * 100;
          }
        }

        fetch(config.progressUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfNode ? csrfNode.value : '',
          },
          body: JSON.stringify({
            course_instance_id: config.courseInstanceId || null,
            data: [{
              activityId: String(config.moduleId || ''),
              completion: messageData.score === 1.0,
              score: (messageData.score || 0) * 100,
              success: (messageData.score || 0) >= 0.7,
              progress: progressValue,
              response: messageData.state || null,
            }],
          }),
        }).catch(function (error) {
          console.error('Error updating module progress:', error);
        });
      }
    });
  });
})();
