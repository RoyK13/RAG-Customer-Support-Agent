# Build context is the repository root: the build reads data/*/dataset.yaml and
# eval/results/*/latest.json to render the evaluation table.
FROM node:24-alpine AS build
WORKDIR /repo/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY data/halden/dataset.yaml /repo/data/halden/dataset.yaml
COPY data/fastapi/dataset.yaml /repo/data/fastapi/dataset.yaml
COPY eval/results /repo/eval/results
ARG VITE_API_URL=http://localhost:8000
ARG VITE_GITHUB_URL=
ENV VITE_API_URL=$VITE_API_URL VITE_GITHUB_URL=$VITE_GITHUB_URL
RUN npm run build

FROM nginx:1.29-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/web/dist /usr/share/nginx/html
EXPOSE 80
