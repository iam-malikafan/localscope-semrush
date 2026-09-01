(() => {
  const script = document.currentScript;

  if (!script) {
    return;
  }

  const upstreamUrl = script.dataset.upstreamUrl;

  if (!upstreamUrl) {
    return;
  }

  const upstreamOrigin = new URL(upstreamUrl).origin;

  const localOrigin = window.location.origin;

  function mapExternalUrl(url) {
    const encodedHost = encodeURIComponent(url.host);

    return (
      `${localOrigin}/proxy-external/` +
      `${url.protocol.slice(0, -1)}/` +
      `${encodedHost}` +
      `${url.pathname}` +
      `${url.search}` +
      `${url.hash}`
    );
  }

  function isLocalScopeHost(url) {
    return (
      url.hostname === window.location.hostname ||
      url.hostname === "127.0.0.1" ||
      url.hostname === "localhost"
    );
  }

  function normalizeLocalScopeUrl(url) {
    let path = url.pathname;

    const marker = "/proxy-external/";

    /*
     * Example broken path:
     *
     * /proxy-external/http/127.0.0.1/
     * proxy-external/https/example.com/file
     *
     * Keep the innermost proxy-external
     * route.
     */
    const lastProxyIndex = path.lastIndexOf(marker);

    if (lastProxyIndex > 0) {
      path = path.slice(lastProxyIndex);
    }

    /*
     * Always normalize localhost URLs
     * onto LocalScope's actual origin,
     * including the correct :8000 port.
     */
    return localOrigin + path + url.search + url.hash;
  }

  function mapUrl(value) {

    try {
      const url = new URL(value, upstreamUrl);

      // -------------------------
      // LocalScope / localhost
      // -------------------------

      if (isLocalScopeHost(url)) {
        return normalizeLocalScopeUrl(url);
      }

      // -------------------------
      // Main Semrush domain
      // -------------------------

      if (url.origin === upstreamOrigin) {
        return localOrigin + url.pathname + url.search + url.hash;
      }

      // -------------------------
      // Genuine external domain
      // -------------------------

      return mapExternalUrl(url);
    } catch (error) {
      console.warn("LocalScope could not map URL:", value, error);

      return value;
    }
  }

  // -------------------------
  // fetch()
  // -------------------------

const originalFetch =
    window.fetch.bind(window);


window.fetch = function (
    input,
    init
) {

    try {

        /*
         * Always create the request first
         * using the browser's normal logic.
         *
         * This preserves:
         * method
         * body
         * credentials
         * headers
         * mode
         * redirect
         * referrer
         * etc.
         */

        const originalRequest =
            new Request(
                input,
                init
            );


        const mappedUrl =
            mapUrl(
                originalRequest.url
            );


        /*
         * If no mapping is required,
         * send the original Request.
         */

        if (
            mappedUrl
            === originalRequest.url
        ) {

            return originalFetch(
                originalRequest
            );
        }


        /*
         * Clone the complete request but
         * replace only its URL.
         */

        const mappedRequest =
            new Request(
                mappedUrl,
                originalRequest
            );


        return originalFetch(
            mappedRequest
        );


    } catch (error) {

        console.error(
            "LocalScope fetch mapping failed:",
            error
        );


        return originalFetch(
            input,
            init
        );
    }
};

  // -------------------------
  // XMLHttpRequest
  // -------------------------

  const originalXhrOpen = XMLHttpRequest.prototype.open;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    const mappedUrl = mapUrl(url);

    return originalXhrOpen.call(this, method, mappedUrl, ...rest);
  };

  // -------------------------
  // WebSocket
  // -------------------------

  const OriginalWebSocket = window.WebSocket;

  function mapWebSocketUrl(value) {
    try {
      const url = new URL(value, upstreamUrl);

      let upstreamWsUrl = url.href;

      // Convert normal HTTP schemes
      // into WebSocket schemes.
      if (url.protocol === "https:") {
        upstreamWsUrl =
          "wss://" + url.host + url.pathname + url.search + url.hash;
      } else if (url.protocol === "http:") {
        upstreamWsUrl =
          "ws://" + url.host + url.pathname + url.search + url.hash;
      }

      // LocalScope itself should use
      // ws:// when running over HTTP,
      // and wss:// when running over HTTPS.
      const localWsProtocol =
        window.location.protocol === "https:" ? "wss:" : "ws:";

      return (
        `${localWsProtocol}//` +
        `${window.location.host}` +
        `/ws-proxy/` +
        encodeURIComponent(upstreamWsUrl)
      );
    } catch (error) {
      console.warn("LocalScope could not map WebSocket URL:", value, error);

      return value;
    }
  }

  window.WebSocket = function (url, protocols) {
    const mappedUrl = mapWebSocketUrl(url);

    if (protocols === undefined) {
      return new OriginalWebSocket(mappedUrl);
    }

    return new OriginalWebSocket(mappedUrl, protocols);
  };

  window.WebSocket.prototype = OriginalWebSocket.prototype;

  Object.defineProperty(window.WebSocket, "CONNECTING", {
    value: OriginalWebSocket.CONNECTING,
  });

  Object.defineProperty(window.WebSocket, "OPEN", {
    value: OriginalWebSocket.OPEN,
  });

  Object.defineProperty(window.WebSocket, "CLOSING", {
    value: OriginalWebSocket.CLOSING,
  });

  Object.defineProperty(window.WebSocket, "CLOSED", {
    value: OriginalWebSocket.CLOSED,
  });

  // -------------------------
  // navigator.sendBeacon()
  // -------------------------

  if (navigator.sendBeacon) {
    const originalSendBeacon = navigator.sendBeacon.bind(navigator);

    navigator.sendBeacon = function (url, data) {
      const mappedUrl = mapUrl(url);

      return originalSendBeacon(mappedUrl, data);
    };
  }

  // -------------------------
  // EventSource / SSE
  // -------------------------

  if (window.EventSource) {
    const OriginalEventSource = window.EventSource;

    window.EventSource = function (url, options) {
      const mappedUrl = mapUrl(url);

      return new OriginalEventSource(mappedUrl, options);
    };

    window.EventSource.prototype = OriginalEventSource.prototype;
  }

  // -------------------------
  // Dynamic DOM resource URLs
  // -------------------------

  function patchUrlProperty(prototype, propertyName) {
    const descriptor = Object.getOwnPropertyDescriptor(prototype, propertyName);

    if (!descriptor || !descriptor.get || !descriptor.set) {
      return;
    }

    Object.defineProperty(prototype, propertyName, {
      configurable: descriptor.configurable,

      enumerable: descriptor.enumerable,

      get: descriptor.get,

      set(value) {
        const mappedValue = mapUrl(value);

        return descriptor.set.call(this, mappedValue);
      },
    });
  }

  patchUrlProperty(HTMLScriptElement.prototype, "src");

  patchUrlProperty(HTMLImageElement.prototype, "src");

  patchUrlProperty(HTMLMediaElement.prototype, "src");

  patchUrlProperty(HTMLVideoElement.prototype, "poster");

  patchUrlProperty(HTMLSourceElement.prototype, "src");

  patchUrlProperty(HTMLIFrameElement.prototype, "src");

  patchUrlProperty(HTMLLinkElement.prototype, "href");
  patchUrlProperty(HTMLAnchorElement.prototype, "href");

  patchUrlProperty(HTMLFormElement.prototype, "action");

  const originalSetAttribute = Element.prototype.setAttribute;

  Element.prototype.setAttribute = function (name, value) {
    const attribute = String(name).toLowerCase();

    const tag = this.tagName?.toLowerCase();

    const urlAttributes = {
      script: ["src"],
      img: ["src"],
      video: ["src", "poster"],
      audio: ["src"],
      source: ["src"],
      iframe: ["src"],
      link: ["href"],
      form: ["action"],
      a: ["href"],
    };

    if (urlAttributes[tag]?.includes(attribute)) {
      value = mapUrl(value);
    }

    return originalSetAttribute.call(this, name, value);
  };

  // -------------------------
  // Worker
  // -------------------------

  if (window.Worker) {
    const OriginalWorker = window.Worker;

    window.Worker = function (url, options) {
      const mappedUrl = mapUrl(url);

      return new OriginalWorker(mappedUrl, options);
    };

    window.Worker.prototype = OriginalWorker.prototype;
  }

  // -------------------------
  // SharedWorker
  // -------------------------

  if (window.SharedWorker) {
    const OriginalSharedWorker = window.SharedWorker;

    window.SharedWorker = function (url, options) {
      const mappedUrl = mapUrl(url);

      return new OriginalSharedWorker(mappedUrl, options);
    };

    window.SharedWorker.prototype = OriginalSharedWorker.prototype;
  }

  console.log("LocalScope runtime proxy active");
})();
