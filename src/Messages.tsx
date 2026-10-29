import Alert from "react-bootstrap/Alert";
import type { Message } from "./MessageContext";

type Props = {
  messages: Array<Message>;
  // Without it, messages can't be dismissed.
  onChange?: (messages: Array<Message>) => void;
};

export default function Messages({ messages, onChange }: Props) {
  const hideMessage = (i: number) =>
    onChange?.(messages.slice(0, i).concat(messages.slice(i + 1)));
  return (
    <>
      {messages.map((message, i) => (
        <Alert
          variant={message.variant}
          onClose={() => hideMessage(i)}
          dismissible={onChange != null}
          key={i}
        >
          {message.text}
        </Alert>
      ))}
    </>
  );
}
