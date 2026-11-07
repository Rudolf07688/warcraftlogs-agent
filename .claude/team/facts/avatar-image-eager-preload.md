---
id: avatar-image-eager-preload
anchors: [file:frontend/src/components/ui/avatar.tsx, file:frontend/src/components/profile/ClassAvatar.tsx]
by: dev-1 Ansel
verified: b833929 2026-11-07
---
The registry AvatarImage (radix) preloads its src with new window.Image() before showing it, so
loading='lazy' has no effect. ClassAvatar (075) puts a plain lazy <img> absolutely over
AvatarFallback instead; radix keeps the fallback rendered because no AvatarImage reports
'loaded'.
