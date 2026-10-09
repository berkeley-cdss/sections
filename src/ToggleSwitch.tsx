import { useId, useState } from "react";
import Form from "react-bootstrap/Form";

type Props = {
  defaultChecked: boolean;
  onChange: (checked: boolean) => void;
  offText?: string | null;
  onText?: string | null;
};

// A Bootstrap switch, labeled with onText/offText for its current state.
export default function ToggleSwitch({ defaultChecked, onChange, offText, onText }: Props) {
  const id = useId();
  const [checked, setChecked] = useState(defaultChecked);
  // Follow defaultChecked when it changes, e.g. after the server's config reloads.
  const [prevDefaultChecked, setPrevDefaultChecked] = useState(defaultChecked);
  if (defaultChecked !== prevDefaultChecked) {
    setPrevDefaultChecked(defaultChecked);
    setChecked(defaultChecked);
  }

  return (
    <Form.Check
      type="switch"
      id={id}
      checked={checked}
      label={(checked ? onText : offText) ?? undefined}
      onChange={(e) => {
        setChecked(e.target.checked);
        onChange(e.target.checked);
      }}
    />
  );
}
