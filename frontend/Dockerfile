FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# pnpm のバージョンは package.json の packageManager で固定する。
# 以前は pnpm@latest だったが、pnpm 11 から package.json の "pnpm" フィールドが
# 読まれなくなり onlyBuiltDependencies が無視され、msw のビルドスクリプトが
# 実行されないまま ERR_PNPM_IGNORED_BUILDS でビルドが落ちるようになった。
RUN corepack install && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:alpine
RUN apk upgrade --no-cache
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /usr/share/nginx/html && \
    sed -i 's|/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf
EXPOSE 80
USER nginx
