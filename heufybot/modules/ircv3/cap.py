from twisted.plugin import IPlugin
from heufybot.moduleinterface import BotModule, IBotModule
from zope.interface import implements


class IRCv3Cap(BotModule):
    implements(IPlugin, IBotModule)

    name = "Cap"
    core = True
    capabilities = {}
    coreCapabilities = ["multi-prefix"]  # Enable multi-prefix by default since it's handled in the core

    def actions(self):
        return [ ("prelogin", 1, self.enableCapabilities),
                 ("disconnect", 1, self.clearCapabilities),
                 ("pre-handlecommand-CAP", 1, self.handleCap),
                 ("pre-handlenumeric-401", 1, self.handleNotSupported),
                 ("has-cap-enabled", 1, self.checkCapEnabled),
                 ("cap-handler-finished", 1, self.handleCapHandlerFinished) ]

    def enableCapabilities(self, server):
        if server in self.capabilities:
            self.bot.log.warn("[{server}] Trying to request capabilities, but capabilities have already been "
                              "requested!")
            return

        self.capabilities[server] = {
            "initializing": True,
            "available": self.coreCapabilities,
            "requested": [],
            "enabled": [],
            "finished": []
        }

        caps = []
        self.bot.moduleHandler.runProcessingAction("listcaps", server, caps)
        self.capabilities[server]["available"].extend(caps)
        self.bot.log.info("[{server}] Requesting available capabilities...", server=server)
        self.bot.servers[server].sendMessage("CAP", "LS")

    def clearCapabilities(self, server):
        if server in self.capabilities:
            del self.capabilities[server]

    def handleCap(self, server, nick, ident, host, params):
        if params[1] == "LS":
            self.bot.log.info("[{server}] Received CAP LS reply, server supports capabilities: {caps}.", server=server,
                              caps=params[2])
            serverCaps = _parseCapReply(params[2])
            for reqCap in [x for x in self.capabilities[server]["available"] if x in serverCaps]:
                self.capabilities[server]["requested"].append(reqCap)
            self._checkNegotiationFinished(server)
            if self.capabilities[server]["initializing"]:
                toRequest = " ".join(self.capabilities[server]["requested"])
                self.bot.log.info("[{server}] Requesting capabilities: {caps}...", server=server, caps=toRequest)
                self.bot.servers[server].sendMessage("CAP", "REQ", toRequest)
        elif params[1] == "ACK" or params[1] == "NAK":
            capList = _parseCapReply(params[2])
            self.capabilities[server]["requested"] = [x for x in self.capabilities[server]["requested"] if x not in
                                                      capList]
            if params[1] == "ACK":
                for capName in capList:
                    if capName not in self.capabilities[server]["enabled"]:
                        self.capabilities[server]["enabled"].append(capName)
                    if capName in self.coreCapabilities and capName not in self.capabilities[server]["finished"]:
                        self.capabilities[server]["finished"].append(capName)

                self.bot.log.info("[{server}] Acknowledged capability changes: {caps}.", server=server, caps=params[2])
                self.bot.moduleHandler.runGenericAction("caps-acknowledged", server, capList)
            else:
                self.bot.log.info("[{server}] Rejected capability changes: {caps}.", server=server, caps=params[2])
                self.bot.moduleHandler.runGenericAction("caps-rejected", server, capList)
            self._checkNegotiationFinished(server)

    def handleNotSupported(self, server, prefix, params):
        # This is assuming the numeric is even sent to begin with, which some unsupported IRCds don't even seem to do.
        if params[0] == "CAP":
            self.bot.log.info("[{server}] Server does not support capability negotiation.", server=server)
            self.capabilities[server]["initializing"] = False

    def handleCapHandlerFinished(self, server, capName):
        self.capabilities[server]["finished"].append(capName)
        self._checkNegotiationFinished(server)

    def checkCapEnabled(self, server, capName):
        if server not in self.capabilities:
            return False
        return capName in self.capabilities[server]["enabled"]

    def _checkNegotiationFinished(self, server):
        if not self.capabilities[server]["initializing"] or len(self.capabilities[server]["requested"]) != 0:
            return

        if set(self.capabilities[server]["enabled"]) == set(self.capabilities[server]["finished"]):
            self.bot.servers[server].sendMessage("CAP", "END")
            self.bot.log.info("[{server}] Capability negotiation completed.", server=server)
            self.capabilities[server]["initializing"] = False


def _parseCapReply(reply):
    parsedReply = {}
    for serverCap in reply.split():
        if "=" in serverCap:
            key, value = serverCap.split("=")
        else:
            key = serverCap
            value = None
        parsedReply[key] = value
    return parsedReply


cap = IRCv3Cap()
