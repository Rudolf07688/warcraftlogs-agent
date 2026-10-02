# Frontend: React + Vite dev server (basic, for local testing).
# Uses a glibc (Debian) base rather than Alpine/musl: Tailwind v4's native Rust
# binaries (@tailwindcss/oxide, lightningcss) and rollup/esbuild ship glibc prebuilts
# and SIGBUS/segfault on musl, so Alpine crashes `vite` at startup.
FROM node:22-slim

WORKDIR /app

# Copy the lockfile too so installs are reproducible and platform-correct.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
