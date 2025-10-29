// Service Worker pour NonoTalk
const CACHE_NAME = 'nonotalk-v1'
const urlsToCache = [
  '/',
  '/static/js/bundle.js',
  '/static/css/main.css',
  '/logo.png'
]

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache)
      })
  )
})

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response
        }
        return fetch(event.request)
      })
  )
})

// Gestion des notifications push
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'Nouveau message de Nono',
    icon: '/logo.png',
    badge: '/logo.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'Ouvrir NonoTalk',
        icon: '/logo.png'
      },
      {
        action: 'close',
        title: 'Fermer',
        icon: '/logo.png'
      }
    ]
  }

  event.waitUntil(
    self.registration.showNotification('NonoTalk', options)
  )
})

self.addEventListener('notificationclick', event => {
  event.notification.close()

  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    )
  }
})

