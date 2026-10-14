# Frontend image with two targets:
#   dev  — the Vite dev server with hot reload (what docker compose uses locally)
#   prod — a static production build served by nginx, which also proxies /api and /ws
#          to the backend (PERF-011: minified, code-split bundle instead of dev modules)
#
# The Node stages use a glibc (Debian) base rather than Alpine/musl: Tailwind v4's native
# Rust binaries (@tailwindcss/oxide, lightningcss) and rollup/esbuild ship glibc prebuilts
# and SIGBUS/segfault on musl, so Alpine crashes `vite` at startup.

FROM node:22-slim AS deps
WORKDIR /app
# Copy the lockfile too so installs are reproducible and platform-correct.
COPY package.json package-lock.json* ./
RUN npm install

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM deps AS build
COPY . .
RUN npm run build

# nginx only serves static files, so the musl caveat above doesn't apply here.
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
