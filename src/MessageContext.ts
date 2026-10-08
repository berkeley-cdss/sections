import * as React from "react";

type MessageContextType = {
  pushMessage: (message: string) => void;
};

export default React.createContext<MessageContextType>({
  pushMessage: () => {},
});
