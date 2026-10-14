FROM node:22-slim
WORKDIR /repo
COPY docs/contracts /repo/docs/contracts
COPY apps/frontend /repo/apps/frontend
WORKDIR /repo/apps/frontend
# Empty means the browser calls same-origin /api/v1/*, served by the Next proxy route.
# The Core token is a runtime server env (CORE_API_TOKEN), never baked into the bundle.
ARG NEXT_PUBLIC_API_BASE_URL=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm install && npm run gen:types && npm run build
ENV PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
