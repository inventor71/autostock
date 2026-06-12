import { Permission } from "@/permission"
import { PermissionID } from "@/permission/schema"
import { Effect, Option } from "effect"
import { HttpServerRequest } from "effect/unstable/http"
import { HttpApiBuilder } from "effect/unstable/httpapi"
import { InstanceHttpApi } from "../api"
import { PermissionNotFoundError } from "../errors"
import * as AutostockWebAuthn from "@/server/autostock/webauthn"

export const permissionHandlers = HttpApiBuilder.group(InstanceHttpApi, "permission", (handlers) =>
  Effect.gen(function* () {
    const svc = yield* Permission.Service

    const list = Effect.fn("PermissionHttpApi.list")(function* () {
      return yield* svc.list()
    })

    const reply = Effect.fn("PermissionHttpApi.reply")(function* (ctx: {
      params: { requestID: PermissionID }
      payload: Permission.ReplyBody
    }) {
      // F71 U2: a REMOTE approval of a mutating autostock permission requires a fresh
      // WebAuthn assertion (x-autostock-webauthn). Loopback/in-process (desktop TUI) and
      // rejections pass through untouched. Server-side — a tampered client can't skip it.
      const request = yield* HttpServerRequest.HttpServerRequest
      const pending = yield* svc.list()
      const info = pending.find((p) => p.id === ctx.params.requestID)
      const denial = yield* Effect.promise(() =>
        AutostockWebAuthn.checkReply({
          reply: ctx.payload.reply,
          remoteAddress: Option.getOrUndefined(request.remoteAddress),
          permission: info?.permission,
          header: request.headers["x-autostock-webauthn"],
        }),
      )
      if (denial !== null) {
        return yield* Effect.fail(
          new PermissionNotFoundError({ requestID: String(ctx.params.requestID), message: denial }),
        )
      }

      yield* svc
        .reply({
          requestID: ctx.params.requestID,
          reply: ctx.payload.reply,
          message: ctx.payload.message,
        })
        .pipe(
          Effect.catchTag("Permission.NotFoundError", (error) =>
            Effect.fail(
              new PermissionNotFoundError({
                requestID: String(error.requestID),
                message: `Permission request not found: ${error.requestID}`,
              }),
            ),
          ),
        )
      return true
    })

    return handlers.handle("list", list).handle("reply", reply)
  }),
)
