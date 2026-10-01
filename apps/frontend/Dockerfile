FROM node:22-slim
WORKDIR /repo
COPY docs/contracts /repo/docs/contracts
COPY apps/frontend /repo/apps/frontend
WORKDIR /repo/apps/frontend
RUN npm install && npm run gen:types && npm run build
ENV PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
