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
    var browserSessionId = uuid();
    var frameStartedAt = Date.now();
    var attentionState = (document.hidden || (typeof document.hasFocus === 'function' && !document.hasFocus()))
      ? 'blurred'
      : 'focused';

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

    function iframeUrlSummary() {
      var iframeSrc = iframe.getAttribute('src') || '';
      if (!iframeSrc) {
        return {};
      }
      try {
        var parsed = new URL(iframeSrc, window.location.origin);
        return {
          iframe_origin: parsed.origin,
          iframe_path: parsed.pathname,
        };
      } catch (error) {
        return {};
      }
    }

    function sessionPayload(reason, extra) {
      return Object.assign({
        browser_session_id: browserSessionId,
        client_event_id: uuid(),
        client_timestamp: new Date().toISOString(),
        elapsed_ms: Date.now() - frameStartedAt,
        reason: reason || '',
        visibility_state: document.visibilityState || '',
        document_hidden: Boolean(document.hidden),
        window_focused: typeof document.hasFocus === 'function' ? document.hasFocus() : null,
      }, iframeUrlSummary(), extra || {});
    }

    function recordSessionEvent(eventType, reason, extra) {
      if (config.previewMode || !config.sessionEventUrl) {
        return;
      }

      fetch(config.sessionEventUrl, {
        method: 'POST',
        keepalive: true,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfNode ? csrfNode.value : '',
        },
        body: JSON.stringify({
          event_type: eventType,
          payload: sessionPayload(reason, extra),
        }),
      }).catch(function (error) {
        console.warn('Error recording module session event:', error);
      });
    }

    function setAttentionState(nextState, reason) {
      if (nextState === attentionState) {
        return;
      }
      attentionState = nextState;
      recordSessionEvent(
        nextState === 'blurred' ? 'tab_blur' : 'tab_focus',
        reason,
        { attention_state: nextState }
      );
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
      if (iframe.getAttribute('src')) {
        recordSessionEvent('iframe_load', 'iframe_load');
      }
      probeSplice();
      setTimeout(probeSplice, 900);
      setTimeout(probeSplice, 2400);
    });

    document.addEventListener('visibilitychange', function () {
      setAttentionState(document.hidden ? 'blurred' : 'focused', document.hidden ? 'visibility_hidden' : 'visibility_visible');
    });

    window.addEventListener('blur', function () {
      setAttentionState('blurred', 'window_blur');
    });

    window.addEventListener('focus', function () {
      setAttentionState('focused', 'window_focus');
    });

    window.addEventListener('pagehide', function () {
      setAttentionState('blurred', 'pagehide');
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

        var hasScoreText = Boolean(
          messageData.state &&
          messageData.state.scoreText &&
          messageData.state.scoreText.indexOf('/') !== -1
        );
        var isPcexTrackingOnly = Boolean(
          messageData.state &&
          messageData.state.trackingData &&
          !hasScoreText &&
          (typeof messageData.score !== 'number' || messageData.score === 0)
        );
        if (isPcexTrackingOnly) {
          return;
        }

        var progressValue = 0;
        if (hasScoreText) {
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
