FROM node:22-slim
WORKDIR /repo
COPY docs/contracts /repo/docs/contracts
COPY apps/frontend /repo/apps/frontend
WORKDIR /repo/apps/frontend
ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
ARG NEXT_PUBLIC_CORE_API_TOKEN=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_CORE_API_TOKEN=$NEXT_PUBLIC_CORE_API_TOKEN
RUN npm install && npm run gen:types && npm run build
ENV PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
