FROM node:24-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

FROM node:24-alpine
WORKDIR /app
COPY --from=build /app/build ./build
ENV HOST=0.0.0.0 PORT=3000
EXPOSE 3000
CMD ["node", "build"]
