import * as React from "react";

// Bootstrap alert colors: errors are red unless a message says otherwise.
export type MessageVariant = "danger" | "success" | "info";

export type Message = {
  text: string;
  variant: MessageVariant;
};

type MessageContextType = {
  pushMessage: (message: string, variant?: MessageVariant) => void;
};

export default React.createContext<MessageContextType>({
  pushMessage: () => {},
});
