FROM node:20-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV KYM_API_URL=http://api:8000
RUN npm run build

FROM node:20-slim
WORKDIR /web
ENV NODE_ENV=production KYM_API_URL=http://api:8000
COPY --from=build /web ./
EXPOSE 3000
CMD ["npm", "run", "start"]
